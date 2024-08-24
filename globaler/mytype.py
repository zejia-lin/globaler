from enum import Enum

class JSONSerializableEnum(Enum):
    def __str__(self):
        """Serialize as the enum's name"""
        return self.name

    def __repr__(self):
        """Provide a representation that is also JSON serializable"""
        return f'"{self.name}"'

    @classmethod
    def from_json(cls, value):
        """eserialize from a string name to the enum instance"""
        return cls[value]

    def to_json(self):
        """Convert to a JSON-compatible format (string in this case)"""
        return self.name