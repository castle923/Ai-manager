"""Include the reviewed public notebook sources in installed distributions."""
from pathlib import Path
import runpy
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildWithColabResources(build_py):
    def run(self):
        super().run()
        root = Path(__file__).resolve().parent
        stage = runpy.run_path(str(root / 'scripts/stage_colab_resources.py'))['stage']
        self.colab_outputs = stage(root, Path(self.build_lib) / 'ai_manager')

    def get_outputs(self, include_bytecode=1):
        return super().get_outputs(include_bytecode) + [str(p) for p in getattr(self, 'colab_outputs', ())]


setup(cmdclass={'build_py': BuildWithColabResources})
