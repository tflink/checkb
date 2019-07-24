from setuptools import setup, Command
from utils import build

class PyTest(Command):
    user_options = []
    def initialize_options(self):
        pass
    def finalize_options(self):
        pass
    def run(self):
        import subprocess
        import sys
        if (sys.version_info > (3, 0)):
                errno = subprocess.call(['pytest-3'])
        else:
                errno = subprocess.call(['py.test'])
        raise SystemExit(errno)


setup(name='checkb',
      version=build.find_version(),
      description='runner for build checks',
      author='Tim Flink',
      author_email='tflink@fedoraproject.org',
      license='GPLv2+',
      url='https://pagure.io/checkb',
      packages=['checkb', 'checkb.directives', 'checkb.ext',
                'checkb.ext.fedora', 'checkb.ext.disposable'],
      package_data={'checkb': ['report_templates/*.j2']},
      package_dir={'checkb':'checkb'},
      include_package_data=True,
      cmdclass={'test': PyTest},
      entry_points=dict(console_scripts=['runtask=checkb.main:main',
                                         'checkb_result=checkb.checkb_result:main']),
      install_requires = [
      ]
)
