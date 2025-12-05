
VERSION = (0, 9, 3)
__version__ = '.'.join(map(str, VERSION))


try:
    #build distribution will fail, since maya modules aren't present.
    #IF the toml gets the versioning info from the module.
    from .core import *
except ModuleNotFoundError:
    pass

