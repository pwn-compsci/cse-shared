import json

def snake_to_camel(s):
    parts = s.split('_')
    return parts[0] + ''.join(word.capitalize() for word in parts[1:])

def process_json(data):
    for obj in data:
        # Convert snake_case field names to camelCase
        for field in ['field1', 'field2', 'field3', 'field4']:
            if field in obj and '_' in obj[field]:
                obj[field] = snake_to_camel(obj[field])

        new_file_values = []
        subtypes = set()

        for line in obj['file_values']:
            parts = line.split(',')

            # Remove 4th column (2nd-to-last) if it ends in A or B
            if parts[-2].endswith('A') or parts[-2].endswith('B'):
                parts = parts[:3] + [parts[-1]]
            # Otherwise, keep the full line
            new_line = ','.join(parts)
            new_file_values.append(new_line)
            subtypes.add(parts[-1])

        obj['file_values'] = new_file_values
        obj['subtypes'] = sorted(subtypes)

    return data

def main():
    input_file = "io_subtypes.json"
    output_file = "io_subtypes_modified.json"

    with open(input_file, 'r') as f:
        data = json.load(f)

    updated_data = process_json(data)

    with open(output_file, 'w') as f:
        json.dump(updated_data, f, indent=2)

    print(f"Updated JSON written to: {output_file}")

if __name__ == "__main__":
    main()
