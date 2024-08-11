def disable_if(condition):
    def decorator(func):
        if condition:
            return func
        else:
            return lambda *args, **kwargs: None
    return decorator

# Example Usage
DEBUG = False

@disable_if(DEBUG)
def debug_function():
    print("Debug function is running.")

DEBUG = True

debug_function()
debug_function()
