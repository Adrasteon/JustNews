
# Path to the requirements file
requirements_file = "agents/scout/requirements.txt"

# Read the requirements file
with open(requirements_file) as file:
    lines = file.readlines()

# Prepare updated requirements without enforcing hashes
updated_lines = []
for line in lines:
    line = line.strip()
    if line and not line.startswith("#"):
        updated_lines.append(line)
    else:
        updated_lines.append(line)

# Write updated requirements back to the file
with open(requirements_file, "w") as file:
    file.write("\n".join(updated_lines))

print("Requirements updated successfully.")
