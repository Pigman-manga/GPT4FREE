import os

def detect_replit():
    """
    Detects whether the code is running in a Replit environment.

    Returns:
        bool: True if running in a Replit environment, False otherwise.
    """
    if "REPL_OWNER" in os.environ:
        return True
    return False

if __name__ == "__main__":
    if detect_replit():
        print("We are running on replit")