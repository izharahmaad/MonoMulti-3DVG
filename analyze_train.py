import ast
import collections
import glob
import json
import re

TRAIN_DIR = r"C:\Datasets\VLMOD_TRAIN_EXTRACT\MonoMulti3D\train"

files = glob.glob(TRAIN_DIR + r"\*.json")

property_types = collections.Counter()
property_values = collections.Counter()
label_counts = []
object_classes = collections.Counter()
colours = collections.Counter()
occlusions = collections.Counter()
directions = collections.Counter()
parse_errors = 0
annotation_count = 0

for file_path in files:
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    annotations = data[0]

    for annotation in annotations:
        annotation_count += 1

        for prop in annotation.get("public_properties", []):
            if " : " in prop:
                key, value = prop.split(" : ", 1)
                property_types[key] += 1
                property_values[(key, value)] += 1
            else:
                property_types["unknown"] += 1

        labels = annotation.get("label_3", [])
        label_counts.append(len(labels))

        for item in labels:
            try:
                obj = ast.literal_eval(item)

                if len(obj) > 0:
                    object_classes[str(obj[0])] += 1

                if len(obj) > 1:
                    occlusions[str(obj[1])] += 1

                if len(obj) > 3:
                    directions[str(obj[3])] += 1

                if len(obj) > 14:
                    colours[str(obj[14])] += 1

            except (ValueError, SyntaxError):
                parse_errors += 1

print("\n" + "=" * 65)
print("MONOMULTI3D TRAINING DATA SUMMARY")
print("=" * 65)

print(f"\nTraining files: {len(files)}")
print(f"Total annotations: {annotation_count}")
print(f"Objects in label_3: {sum(label_counts)}")
print(f"Average matched objects per annotation: {sum(label_counts) / len(label_counts):.2f}")
print(f"Minimum matched objects: {min(label_counts)}")
print(f"Maximum matched objects: {max(label_counts)}")
print(f"Label parsing errors: {parse_errors}")

print("\nPROPERTY TYPES")
for key, count in property_types.most_common():
    print(f"{key:20} {count}")

print("\nOBJECT CLASSES FOUND IN label_3")
for key, count in object_classes.most_common():
    print(f"{key:20} {count}")

print("\nCOLOURS FOUND IN label_3")
for key, count in colours.most_common():
    print(f"{key:20} {count}")

print("\nOCCLUSION VALUES FOUND IN label_3")
for key, count in occlusions.most_common():
    print(f"{key:20} {count}")

print("\nMOST COMMON PROPERTY VALUES")
for (key, value), count in property_values.most_common(100):
    print(f"{key:20} | {value:35} | {count}")

print("\nSAMPLE ANNOTATIONS")
shown = 0

for file_path in files:
    with open(file_path, "r", encoding="utf-8") as file:
        data = json.load(file)

    for annotation in data[0]:
        print("-" * 65)
        print("File:", annotation["image_file_name"])
        print("Description:", annotation["public_description"])
        print("Properties:", annotation["public_properties"])
        print("Matched objects:", len(annotation["label_3"]))

        for label in annotation["label_3"][:3]:
            print(" ", label)

        shown += 1

        if shown == 10:
            break

    if shown == 10:
        break