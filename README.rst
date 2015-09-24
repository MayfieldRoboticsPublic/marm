====
marm
====

`libav* <http://www.ffmpeg.org/>`_ front-end used to:

- Read stored/archived media (e.g. `pcap <http://www.tcpdump.org/pcap.html>`_ed `rtp <https://tools.ietf.org/html/rfc3550>`_ packets).
- Reconstruct frames (e.g. depacketize a frame from its rtp packets).
- Synchronize reconstructed streams of frame data (e.g. audio and video).
- Mux frame stream(s) to a container (e.g. `mkv <http://www.matroska.org/>`_ file) using libav*.

Motivating use case was:

- depacketizing rtp payloads from `mjr <https://github.com/meetecho/janus-gateway>`_ files and 
- muxing them to an mkv file

which you can do e.g. like:

.. code:: python

    import marm
    
    v_pkts = marm.mjr.MJRRTPPacketReader(
        'path/to/video.mjr', 'rb',
        packet_type=marm.vp8.VP8RTPPacket,
    )
    v_width, v_height = marm.rtp.probe_video_dimensions(v_pkts)
    v_pkts.reset()
    v_frame_rate = marm.rtp.estimate_video_frame_rate(v_pkts, window=10)
    v_pkts.reset()
    v_frames = marm.VideoFrames(v_pkts)
    
    a_pkts = marm.mjr.MJRRTPPacketReader(
        'path/to/audio.mjr', 'rb',
        packet_type=marm.opus.OpusRTPPacket,
    )
    a_frames = marm.Frames(a_pkts)
    
    with open('path/to/muxed.mkv', 'wb') as mkv_fo:
        marm.mux_frames(
            mkv_fo,
            audio_profile={
                'encoder_name': 'libopus',
                'bit_rate': 96000,
                'sample_rate': 48000,
                'time_base': (1, 1000),
            },
            audio_packets=a_frames,
            video_profile={
                'encoder_name': 'libpvx',
                'pix_fmt': marm.VideoFrame.PIX_FMT_YUV420P,
                'width': v_width,
                'height': v_height,
                'frame_rate': v_frame_rate,
                'bit_rate': 4000000,
                'time_base': (1, 1000),
            },
            video_packets=v_frames,
        )

deps
----

Devel `libav* <https://www.ffmpeg.org`_:

.. code:: bash

   mkdir ~/ffmpeg
   cd ~/ffmpeg
   ./configure --enable-gpl --enable-version3 --enable-nonfree --enable-gpl --enable-libass --enable-libfaac --enable-libfdk-aac --enable-libmp3lame --enable-libopus --enable-libtheora --enable-libvorbis --enable-libvpx --enable-libx264
   make
   sudo make install

and `libpcap <https://github.com/cisco/libsrtp>`_:

.. code:: bash

   sudo apt-get install libpcap-dev

if you need them

install
-------

If you just want to use it:

.. code:: bash

   pip install marm

but if you are developing then get it:

.. code:: bash

   git clone git@github.com:mayfieldrobotics/marm.git ~/code/marm
   cd marm
   
create a `venv <https://virtualenv.pypa.io/en/latest/>`_:

.. code:: bash

   mkvirtualenv marm
   workon marm
   pip install Cython
   pip install -e .[test]

and test it:

.. code:: bash

   py.test test/ --cov marm --cov-report term-missing --pep8

usage
-----

Typically you'll begin with stored/archived media packets. Assuming e.g. we
have **video** and **audio** `rtp` packets in an `mjr` file(s).

cli
~~~

First create some work dir:

.. code:: bash

   mkdir /tmp/marm

then split source into **10** second parts:

.. code:: bash

   $ marm split fixtures/test/sonic-a.mkv --dur 10.0 /tmp/marm/sonic-a-{part}.mjr
   $ ll /tmp/marm/sonic-a-*.mjr
   $ marm split fixtures/test/sonic-v.mkv --dur 10.0 /tmp/marm/sonic-v-{part}.mjr
   $ ll /tmp/marm/sonic-v-*.mjr

now mux first half to **mkv**:

.. code:: bash

   $ marm mux fixtures/test/sonic-{a,v}-{1,2,3,4,5,6}.mkv /tmp/marm/sonic-1.mkv
   
and then the second half to **mkv**:

.. code:: bash

   $ marm mux -i 1 fixtures/test/sonic-{a,v}-{7,8,9,10,11,12}.mkv /tmp/marm/sonic-2.mkv
   
Finally **concat** the two:

   $ cat > /tmp/marm/sonic.txt <EOH
   /tmp/marm/sonic-1.mkv
   /tmp/marm/sonic-2.mkv
   EOH
   $ ffmpeg -f concat -i /tmp/marm/sonic.txt -c copy /tmp/marm/sonic-concat.mkv

and use the result:

.. code:: bash

   $ ffprobe /tmp/marm/sonic-concat.mkv
   Input #0, matroska,webm, from '/tmp/pytest-of-ai/pytest-58/test_concat_muxed_sonic_v_mjr_0/concat.mkv':
     Metadata:
       ENCODER         : Lavf56.36.100
     Duration: 00:02:00.11, start: 0.007000, bitrate: 338 kb/s
       Stream #0:0: Video: vp8, yuv420p, 320x240, SAR 1:1 DAR 4:3, 30 fps, 30 tbr, 1k tbn, 1k tbc (default)
       Stream #0:1: Audio: opus, 48000 Hz, stereo, fltp (default)
   $ ffplay /tmp/marm/sonic-concat.mkv

code
~~~~

Here's how to do that same in code:

.. code:: python

   import os
   
   import marm
   
   TODO

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
