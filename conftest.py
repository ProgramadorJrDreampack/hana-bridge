"""Asegura que los módulos top-level (config, core, db, ...) sean importables
desde los tests sin importar desde qué directorio se invoque pytest."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
