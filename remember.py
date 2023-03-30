from collections import defaultdict
import os
import openai
import argparse

def get_completion(messages, stop=None):
    completion = openai.ChatCompletion.create(
        model="gpt-4",
        messages=messages,
        stop=stop,
    )
    return completion.choices[0]["message"].to_dict_recursive()

def get_notes():
    return "You have no notes."

def system_prompt(notes_dir):
    return f"""You are a helpful assistant, but your memory does not work. When the user sends you a message, you won't remember anything else they or you have said previously. However, you can take notes.

The user's input will start with a line containing only '\\MESSAGE'.

Your output should contain series of '\\READ' lines, followed by a \\MESSAGE line, followed by one or more lines containing your reply, followed by a series of '\\WRITE' lines.

\\READ <path> - Print the contents of the note at <path> to the console.
\\MESSAGE - Output your reply to the user's message.
\\WRITE <path> - Append the following lines to the note at <path>.

You should preserve any information that might be useful in the future within your conversation notes.

Your notes directory currently:

{notes_tree(notes_dir)}"""

def validate_path(path):
    """ Paths are relative to the notes directory. They must not contain any ".." or ".". """
    return not any([p in path for p in [".", ".."]])

def read_note(notes_dir, path):
    if not validate_path(path):
        return "<invalid path>"
    """ Reads a note relative to the notes directory. Returns <empty> if the note does not exist. """
    try:
        with open(os.path.join(notes_dir, path)) as f:
            return f.read()
    except FileNotFoundError:
        return "<empty>"
    
def write_note(notes_dir, path, content):
    if not validate_path(path):
        return
    print("Writing to", os.path.join(notes_dir, path))
    """ Appends content to a note relative to the notes directory. If the directory does not exist, it is created. If the note does not exist, it is created. """
    os.makedirs(os.path.dirname(os.path.join(notes_dir, path)), exist_ok=True)

    # First check if the file exists, and then check if it ends with a newline
    if os.path.exists(os.path.join(notes_dir, path)):
        with open(os.path.join(notes_dir, path), "r") as f:
            if not f.read().endswith("\n"):
                content = f"\n{content}"
    with open(os.path.join(notes_dir, path), "a") as f:
        f.write(content)

def notes_tree(notes_dir):
    """ Returns a string containing the notes directory as a tree. """
    tree = ""
    curr_dir = ""
    for root, dirs, files in os.walk(notes_dir):
        level = root.replace(notes_dir, "").count(os.sep)
        indent = " " * 4 * (level)
        # Every time a new directory is found, append it to the string like "indent dir/"
        if curr_dir != root:
            tree += f"{indent}{os.path.basename(root)}/\n"
            curr_dir = root
        
        # Every time a file is found, append it to the string like "indent file"
        for f in files:
            tree += f"{indent}    {f}\n"

    # remove the first line
    tree = tree.split("\n", 1)[1]
    # Remove one indent from every line
    tree = "\n".join([line[4:] for line in tree.split("\n")])
    return tree

def parse_read_commands(output):
    read_cmd = "\\READ"
    return [(i, line[len(read_cmd):].strip()) for i, line in enumerate(output.splitlines()) if line.startswith(read_cmd)]

def parse_commands(content):
    lines = content.splitlines()

    command_idxs = [ i for i, line in enumerate(lines) if line.startswith("\\") ]

    # Parse the string for each (i, i+1) pair
    commands_values = [ lines[i:j] for i, j in zip(command_idxs, command_idxs[1:] + [None]) ]
    # Remove the first word from each line if the line begins with \\

    commands = defaultdict(list)
    for i, lines in enumerate(commands_values):
        if lines[0].startswith("\\"):
            commands[lines[0].split(" ")[0]].append("\n".join([" ".join(lines[0].split(" ")[1:])] + lines[1:]))

    return commands

def assistant_loop(notes_dir):
    # Use stateless
    conversation = []
    while True:
        user_input = input("User: ")
        if user_input == "quit":
            break
        conversation.append({"role": "user", "content": user_input})
        system_input = system_prompt(notes_dir)

        assistant_read_commands = get_completion([{ "role": "system", "content": system_input }] + conversation, stop=["\\MESSAGE"])["content"]
        # Get the file outputs
        context_str = ""
        lines = assistant_read_commands.splitlines()

        commands = parse_commands(assistant_read_commands)
        # for i, path in parse_read_commands(assistant_read_commands):
        for path in commands["\\READ"]:
            # Just get first line
            path = path.splitlines()[0]
            context_str += f"\\READ {path}\n{read_note(notes_dir, path)}\n"

        # Append the read commands to the conversation
        conversation.append({"role": "assistant", "content": context_str})
        assistant_output = get_completion([{ "role": "system", "content": system_input }] + conversation)
        conversation.append(assistant_output)

        # Parse the output
        # message, write_cmds = parse_output(assistant_output)
        commands = parse_commands(assistant_output["content"])

        # Write the notes
        # for i, path, content in write_cmds:
        for content in commands["\\WRITE"]:
            path = content.splitlines()[0]
            content = content.splitlines()[1:]
            write_note(notes_dir, path, "\n".join(content))

        message = commands["\\MESSAGE"][0]
        print("Assistant:", message.strip())

def main(notes_dir=None):
    assert notes_dir is not None, "notes_dir must be specified"
    assistant_loop(notes_dir)

if __name__ == "__main__":
    # --notes-dir=./notes
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes-dir", type=str, default="./notes")
    args = parser.parse_args()
    os.makedirs(args.notes_dir, exist_ok=True)
    main(**vars(args))

