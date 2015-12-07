import re
import setuptools.command.test
import subprocess


class PyTest(setuptools.command.test.test):

    user_options = []

    def finalize_options(self):
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest

        pytest.main(self.test_args)

version = (
    re
    .compile(r".*__version__ = '(.*?)'", re.S)
    .match(open('marm/__init__.py').read())
    .group(1)
)

packages = setuptools.find_packages('.', exclude=('test',))

scripts = [
    'script/marm'
]

ext_modules = [
    setuptools.Extension(
        'marm.ext',
        ['marm/ext/gen.c',
         'marm/ext/mux.c',
         'marm/ext/remux.c',
         'marm/ext/scan.c',
         'marm/ext/segment.c',
         'marm/ext/util.c',
         'marm/ext/mpegts.c',
         'marm/ext/ext.pyx'],
        include_dirs=['marm/ext/'],
        extra_compile_args=(
            ['-g', '-O0'] +
            subprocess.check_output(['pkg-config', '--cflags', 'libavformat']).strip().split() +
            subprocess.check_output(['pkg-config', '--cflags', 'libavcodec']).strip().split() +
            subprocess.check_output(['pkg-config', '--cflags', 'libswscale']).strip().split() +
            subprocess.check_output(['pkg-config', '--cflags', 'libavutil']).strip().split()
        ),
        extra_link_args=(
            ['-Wl,-Bsymbolic'] +
            subprocess.check_output(['pkg-config', '--libs', 'libavformat']).strip().split() +
            subprocess.check_output(['pkg-config', '--libs', 'libavcodec']).strip().split() +
            subprocess.check_output(['pkg-config', '--libs', 'libswscale']).strip().split() +
            subprocess.check_output(['pkg-config', '--libs', 'libavutil']).strip().split()
        )
    )
]
try:
    import Cython.Build
    ext_modules = Cython.Build.cythonize(ext_modules)
except ImportError:
    pass


extras_require = {
    'test': [
        'mock >=1.3,<2',
        'pytest >=2.5.2,<3',
        'pytest-cache >=1.0,<2',
        'pytest-cov >=1.7,<2',
        'pytest-pep8 >=1.0.6,<2',
        'pytest-xdist >=1.13.1,<2',
    ],
}

setuptools.setup(
    name='marm',
    version=version,
    url='https://github.com/mayfieldrobotics/marm/',
    author='Mayfield Robotics',
    author_email='dev+marm@mayfieldrobotics.com',
    license='MIT',
    description='Muxing archived media (and more!).',
    long_description=open('README.rst').read(),
    packages=packages,
    scripts=scripts,
    ext_modules=ext_modules,
    platforms='any',
    install_requires=[
        'dpkt >=1.8,<2',
    ],
    tests_require=extras_require['test'],
    extras_require=extras_require,
    cmdclass={'test': PyTest},
    classifiers=[
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
