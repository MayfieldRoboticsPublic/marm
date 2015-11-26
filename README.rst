====
marm
====

.. image:: https://travis-ci.org/mayfieldrobotics/marm.svg
   :target: https://travis-ci.org/mayfieldrobotics/marm

.. image:: https://coveralls.io/repos/mayfieldrobotics/marm/badge.svg?branch=master&service=github
   :target: https://coveralls.io/github/mayfieldrobotics/marm?branch=master

.. image:: https://img.shields.io/pypi/v/marm.svg
   :target: https://pypi.python.org/pypi/marm

Supports *windowed/resumable* transcoding of recorded media codec packets by:

- Reading stored/archived media packets (e.g. `pcap'd <http://www.tcpdump.org/pcap.html>`_ `rtp <https://tools.ietf.org/html/rfc3550>`_)
- Reconstructs media frames (e.g. depacketized encoded frame fragmented by network protocol)
- Synchronizing frame streams (e.g. paired audio and video)
- Muxing frame stream(s) to a container (e.g. `mkv <http://www.matroska.org/>`_ file) using `libav* <https://www.ffmpeg.org/>`_
- Detecting *stitching* information used to seamlessly resume transcoding
- ...

deps
----

Install devel `libav* <https://www.ffmpeg.org/>`_, e.g.:

.. code:: bash

   git clone git://source.ffmpeg.org/ffmpeg.git
   cd ffmpeg
   ./configure\
    --enable-gpl\
    --enable-version3\
    --enable-nonfree\
    --enable-gpl\
    --enable-libass\
    --enable-libfaac\
    --enable-libfdk-aac\
    --enable-libmp3lame\
    --enable-libopus\
    --enable-libtheora\
    --enable-libvorbis\
    --enable-libvpx\
    --enable-libx264
   make
   sudo make install

and `libpcap <https://github.com/the-tcpdump-group/libpcap>`_, e.g.:

.. code:: bash

   sudo apt-get install libpcap-dev

if you need them.

install
-------

If you just want to use it:

.. code:: bash

   pip install marm

but if you are developing then get it:

.. code:: bash

   git clone git@github.com:mayfieldrobotics/marm.git ~/code/marm
   cd ~/code/marm

create a `venv <https://virtualenv.pypa.io/en/latest/>`_:

.. code:: bash

   mkvirtualenv marm
   workon marm
   pip install Cython
   pip install -e .[test]

and test it:

.. code:: bash

   py.test test/ --cov marm --cov-report term-missing --pep8

docs
----

**todo**

release
-------

Tests pass:

.. code:: bash

   py.test test/ --cov marm --cov-report term-missing --pep8

so update ``__version__`` in ``marm/__init__.py``. Commit and tag it:

.. code:: bash

   git commit -am "release v{version}"
   git tag -a v{version} -m "release v{version}"
   git push --tags

and `travis <https://travis-ci.org/mayfieldrobotics/marm>`_ will publish it to `pypi <https://pypi.python.org/pypi/marm/>`_.
