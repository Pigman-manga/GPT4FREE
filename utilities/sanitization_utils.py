import re


def sanitize_username(name):
    """
    Sanitizes the given `name` parameter by converting it to lowercase, removing any non-alphanumeric characters, removing spaces, and truncating it to a maximum length of 64 characters.

    Parameters:
        name (str): The name to be sanitized.

    Returns:
        str: The sanitized name.
    """
    name = name.lower()
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)
    name = name.replace(' ', '')
    name = name[:64]
    return name

def sanitize_prompt(input_string):
    """
    Sanitizes the input string by removing any non-alphanumeric characters.

    Parameters:
        input_string (str): The string to be sanitized.

    Returns:
        str: The sanitized string.
    """
    sanitized_string = re.sub(r'[^\w\s]', '', input_string)
    return sanitized_string