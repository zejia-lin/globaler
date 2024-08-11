import types


def is_class_method(obj):
    return isinstance(obj, types.MethodType)

def is_regular_function(obj):
    return isinstance(obj, types.FunctionType)

