import ast
import collections
import glob
import json
import math
import os
import re
import shutil
import statistics
import zipfile


TRAIN_DIR = r"C:\Datasets\VLMOD_TRAIN_EXTRACT\MonoMulti3D\train"
TEST_DIR = r"C:\Datasets\VLMOD_TEST_EXTRACT\MonoMulti3D\test"
OUTPUT_DIR = "submission_txt"
ZIP_NAME = "MonoMulti3D_submission.zip"
EPSILON = 0.000001


CLASS_WORDS = {
    "car": "car",
    "cars": "car",
    "van": "van",
    "vans": "van",
    "bus": "bus",
    "buses": "bus",
    "truck": "truck",
    "trucks": "truck",
    "pedestrian": "pedestrian",
    "pedestrians": "pedestrian",
    "cyclist": "cyclist",
    "cyclists": "cyclist",
}


def wrap_angle(angle):
    return (angle + math.pi) % (2 * math.pi) - math.pi


def circular_distance(first, second):
    return abs(wrap_angle(first - second))


def parse_object(raw_object):
    if isinstance(raw_object, str):
        parts = raw_object.split()
    else:
        parts = raw_object

    if len(parts) != 16:
        raise ValueError(
            f"Expected 16 object fields, received {len(parts)}: {raw_object}"
        )

    return {
        "class": str(parts[0]).lower(),
        "truncation": int(float(parts[1])),
        "occlusion": int(float(parts[2])),
        "alpha": float(parts[3]),
        "left": float(parts[4]),
        "top": float(parts[5]),
        "right": float(parts[6]),
        "bottom": float(parts[7]),
        "height": float(parts[8]),
        "width": float(parts[9]),
        "length": float(parts[10]),
        "x": float(parts[11]),
        "y": float(parts[12]),
        "z": float(parts[13]),
        "rotation_y": float(parts[14]),
        "colour": str(parts[15]).lower(),
    }


def object_distance(obj):
    return math.sqrt(
        obj["x"] ** 2 + obj["y"] ** 2 + obj["z"] ** 2
    )


def object_centre(obj):
    return (
        (obj["left"] + obj["right"]) / 2.0,
        (obj["top"] + obj["bottom"]) / 2.0,
    )


def property_dictionary(properties):
    result = {}

    for item in properties:
        if " : " in item:
            key, value = item.split(" : ", 1)
            result[key.strip().lower()] = value.strip().lower()

    return result


def parse_size_range(text, dimension):
    pattern = (
        rf"{dimension}[^.]*?"
        rf"([0-9]+(?:\.[0-9]+)?)"
        rf"\s+to\s+"
        rf"([0-9]+(?:\.[0-9]+)?)"
        rf"\s+meters?"
    )

    match = re.search(pattern, text)

    if match is None:
        return None

    return float(match.group(1)), float(match.group(2))


def parse_description(description, known_colours):
    text = description.lower()
    conditions = {}

    for word, object_class in CLASS_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            conditions["objectname"] = object_class
            break

    for colour in sorted(known_colours, key=len, reverse=True):
        if re.search(rf"\b{re.escape(colour)}\b", text):
            conditions["appearance"] = colour
            break

    if "not occluded" in text or "no occluded" in text:
        conditions["occlusion"] = "no occluded"
    elif "partially occluded" in text:
        conditions["occlusion"] = "partially occluded"

    if "side facing me" in text:
        conditions["facing_direction"] = "side facing me"
    elif "facing away from me" in text:
        conditions["facing_direction"] = "facing away from me"
    elif "facing me" in text:
        conditions["facing_direction"] = "facing me"

    places = [
        "top left",
        "top right",
        "bottom left",
        "bottom right",
        "center",
        "left",
        "right",
        "top",
        "bottom",
    ]

    for place in places:
        if re.search(rf"\b{re.escape(place)}\b", text):
            conditions["place"] = place
            break

    for dimension in ["height", "width", "length"]:
        parsed_range = parse_size_range(text, dimension)

        if parsed_range is not None:
            conditions[dimension] = parsed_range

    distance_match = re.search(
        r"(?:within|located within|approximately within)"
        r"\s+(?:approximately\s+)?"
        r"([0-9]+(?:\.[0-9]+)?)"
        r"\s+meters?",
        text,
    )

    if distance_match is not None:
        conditions["distance"] = float(distance_match.group(1))

    return conditions


def build_training_models():
    training_files = glob.glob(os.path.join(TRAIN_DIR, "*.json"))

    if not training_files:
        raise FileNotFoundError(
            f"No training files found in:\n{TRAIN_DIR}"
        )

    known_colours = set()
    direction_angles = collections.defaultdict(list)
    place_centres = collections.defaultdict(list)

    annotation_count = 0
    positive_object_count = 0

    for file_path in training_files:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        for annotation in data[0]:
            annotation_count += 1

            properties = property_dictionary(
                annotation.get("public_properties", [])
            )

            label_objects = []

            for raw_label in annotation.get("label_3", []):
                object_list = ast.literal_eval(raw_label)
                obj = parse_object(object_list)

                label_objects.append(obj)
                known_colours.add(obj["colour"])

            positive_object_count += len(label_objects)

            if "facing_direction" in properties:
                direction_name = properties["facing_direction"]

                for obj in label_objects:
                    direction_angles[direction_name].append(
                        wrap_angle(obj["alpha"])
                    )

            if "place" in properties:
                place_name = properties["place"]

                for obj in label_objects:
                    place_centres[place_name].append(
                        object_centre(obj)
                    )

    direction_prototypes = {}

    for direction_name, angles in direction_angles.items():
        average_sine = statistics.mean(
            math.sin(angle) for angle in angles
        )
        average_cosine = statistics.mean(
            math.cos(angle) for angle in angles
        )

        direction_prototypes[direction_name] = math.atan2(
            average_sine,
            average_cosine,
        )

    place_prototypes = {}

    for place_name, centres in place_centres.items():
        average_x = statistics.mean(
            centre[0] for centre in centres
        )
        average_y = statistics.mean(
            centre[1] for centre in centres
        )

        place_prototypes[place_name] = (
            average_x,
            average_y,
        )

    print("=" * 70)
    print("TRAINING DATA LOADED")
    print("=" * 70)
    print(f"Training files read: {len(training_files)}")
    print(f"Training annotations read: {annotation_count}")
    print(f"Positive label objects read: {positive_object_count}")

    print("\nDirection prototypes:")

    for name, angle in sorted(direction_prototypes.items()):
        print(f"  {name}: {angle:.4f} radians")

    print("\nPlace prototypes:")

    for name, centre in sorted(place_prototypes.items()):
        print(
            f"  {name}: x={centre[0]:.1f}, "
            f"y={centre[1]:.1f}"
        )

    return (
        known_colours,
        direction_prototypes,
        place_prototypes,
    )


def nearest_direction(obj, direction_prototypes):
    if not direction_prototypes:
        return None

    object_angle = wrap_angle(obj["alpha"])

    return min(
        direction_prototypes,
        key=lambda name: circular_distance(
            object_angle,
            direction_prototypes[name],
        ),
    )


def nearest_place(obj, place_prototypes):
    if not place_prototypes:
        return None

    object_x, object_y = object_centre(obj)

    return min(
        place_prototypes,
        key=lambda name: (
            (object_x - place_prototypes[name][0]) ** 2
            + (object_y - place_prototypes[name][1]) ** 2
        ),
    )


def object_matches(
    obj,
    conditions,
    direction_prototypes,
    place_prototypes,
):
    if "objectname" in conditions:
        if obj["class"] != conditions["objectname"]:
            return False

    if "appearance" in conditions:
        if obj["colour"] != conditions["appearance"]:
            return False

    if "occlusion" in conditions:
        if conditions["occlusion"] == "no occluded":
            required_occlusion = 0
        else:
            required_occlusion = 1

        if obj["occlusion"] != required_occlusion:
            return False

    for dimension in ["height", "width", "length"]:
        if dimension not in conditions:
            continue

        minimum, maximum = conditions[dimension]

        if not (
            minimum - EPSILON <= obj[dimension] <= maximum + EPSILON
        ):
            return False

    if "distance" in conditions:
        if object_distance(obj) > conditions["distance"] + 0.15:
            return False

    if "facing_direction" in conditions:
        detected_direction = nearest_direction(
            obj,
            direction_prototypes,
        )

        if detected_direction != conditions["facing_direction"]:
            return False

    if "place" in conditions:
        detected_place = nearest_place(
            obj,
            place_prototypes,
        )

        if detected_place != conditions["place"]:
            return False

    return True


def validate_training(
    known_colours,
    direction_prototypes,
    place_prototypes,
):
    training_files = glob.glob(os.path.join(TRAIN_DIR, "*.json"))

    total_labels = 0
    matched_labels = 0
    missing_properties = collections.Counter()

    for file_path in training_files:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        for annotation in data[0]:
            properties = property_dictionary(
                annotation.get("public_properties", [])
            )

            conditions = parse_description(
                annotation["public_description"],
                known_colours,
            )

            for property_name in properties:
                if property_name not in conditions:
                    missing_properties[property_name] += 1

            for raw_label in annotation.get("label_3", []):
                object_list = ast.literal_eval(raw_label)
                obj = parse_object(object_list)

                total_labels += 1

                if object_matches(
                    obj,
                    conditions,
                    direction_prototypes,
                    place_prototypes,
                ):
                    matched_labels += 1

    if total_labels == 0:
        return 0.0

    score = matched_labels / total_labels

    print("\n" + "=" * 70)
    print("TRAINING VALIDATION")
    print("=" * 70)
    print(
        f"Positive-label validation: "
        f"{matched_labels}/{total_labels} "
        f"({score * 100:.2f}%)"
    )

    if missing_properties:
        print("\nProperties not recovered from descriptions:")

        for name, count in missing_properties.items():
            print(f"  {name}: {count}")

    return score


def create_predictions(
    known_colours,
    direction_prototypes,
    place_prototypes,
):
    test_files = sorted(
        glob.glob(os.path.join(TEST_DIR, "*.json"))
    )

    if not test_files:
        raise FileNotFoundError(
            f"No test files found in:\n{TEST_DIR}"
        )

    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    total_rows = 0
    positive_counts = [0, 0, 0]
    warnings = []

    for file_path in test_files:
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        descriptions = data.get("public_description", [])
        raw_objects = data.get("test_data", [])

        if len(descriptions) != 3:
            raise ValueError(
                f"{os.path.basename(file_path)} has "
                f"{len(descriptions)} descriptions instead of 3."
            )

        all_conditions = []

        for index, description in enumerate(
            descriptions,
            start=1,
        ):
            conditions = parse_description(
                description,
                known_colours,
            )

            if not conditions:
                warnings.append(
                    f"{os.path.basename(file_path)} "
                    f"description {index} could not be parsed: "
                    f"{description}"
                )

            all_conditions.append(conditions)

        rows = []

        for raw_object in raw_objects:
            obj = parse_object(raw_object)
            bits = []

            for conditions in all_conditions:
                match = object_matches(
                    obj,
                    conditions,
                    direction_prototypes,
                    place_prototypes,
                )

                bits.append(1 if match else 0)

            rows.append(
                f"{bits[0]} {bits[1]} {bits[2]}"
            )

            total_rows += 1

            for index, bit in enumerate(bits):
                positive_counts[index] += bit

        stem = os.path.splitext(
            os.path.basename(file_path)
        )[0]

        output_path = os.path.join(
            OUTPUT_DIR,
            stem + ".txt",
        )

        with open(
            output_path,
            "w",
            encoding="utf-8",
            newline="\n",
        ) as output_file:
            output_file.write("\n".join(rows))
            output_file.write("\n")

    with zipfile.ZipFile(
        ZIP_NAME,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for file_name in sorted(os.listdir(OUTPUT_DIR)):
            full_path = os.path.join(
                OUTPUT_DIR,
                file_name,
            )

            archive.write(
                full_path,
                arcname=file_name,
            )

    output_files = glob.glob(
        os.path.join(OUTPUT_DIR, "*.txt")
    )

    print("\n" + "=" * 70)
    print("TEST PREDICTIONS CREATED")
    print("=" * 70)
    print(f"Test files processed: {len(test_files)}")
    print(f"Prediction rows written: {total_rows}")
    print(f"Text files created: {len(output_files)}")
    print(f"Description 1 positive matches: {positive_counts[0]}")
    print(f"Description 2 positive matches: {positive_counts[1]}")
    print(f"Description 3 positive matches: {positive_counts[2]}")
    print(f"Output folder: {os.path.abspath(OUTPUT_DIR)}")
    print(f"ZIP created: {os.path.abspath(ZIP_NAME)}")

    if warnings:
        print("\nWarnings:")

        for warning in warnings[:20]:
            print("  " + warning)

        if len(warnings) > 20:
            print(
                f"  ... plus {len(warnings) - 20} more warnings."
            )
    else:
        print("\nAll test descriptions were parsed successfully.")


def main():
    print("=" * 70)
    print("MONOMULTI3D VLMOD SUBMISSION GENERATOR")
    print("=" * 70)

    (
        known_colours,
        direction_prototypes,
        place_prototypes,
    ) = build_training_models()

    validation_score = validate_training(
        known_colours,
        direction_prototypes,
        place_prototypes,
    )

    if validation_score < 0.95:
        print("\n" + "=" * 70)
        print("STOPPED: VALIDATION SCORE BELOW 95%")
        print("=" * 70)
        print(
            "Predictions were not generated because training "
            "validation is below 95%."
        )
        print(
            "Send the complete terminal output for review."
        )
        return

    create_predictions(
        known_colours,
        direction_prototypes,
        place_prototypes,
    )


if __name__ == "__main__":
    main()