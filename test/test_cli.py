import pytest

import marm.cli


@pytest.mark.parametrize(
    ('stored,pkt_type,pkt_filter,dur,splits,packets'), [
        ('sonic-v.mjr', 'vp8', None, 10.0, 12, 9654),
        ('sonic-a.mjr', 'opus', None, 10.0, 12, 5996),
        ('streets-of-rage.pcap', 'vp8', 'ssrc=3830765780', 2.0, 5, 1239),
        ('streets-of-rage.pcap', 'opus', 'ssrc=4286666423', 2.0, 5, 490),
    ]
)
def test_cli_split(
        tmpdir,
        fixtures,
        stored,
        pkt_type,
        pkt_filter,
        dur,
        splits,
        packets):
    src_path = fixtures.join(stored)

    args = ['split', pkt_type, src_path, tmpdir, '--dur', dur]
    if pkt_filter:
        args.extend(['--filter', pkt_filter])
    parsed = marm.cli.arg_parser.parse_args(map(str, args))
    parsed.cmd(parsed)

    pattern = '{0}*{1}'.format(src_path.purebasename, 'mjr')
    split_paths = list(tmpdir.visit(pattern))

    assert len(split_paths) == splits
    assert sum(
            1
            for split_path in split_paths
            for _ in marm.rtp.RTPPacketReader.open(str(split_path))
        ) == packets


@pytest.mark.parametrize(
    ('a_stored,a_type,a_filter,a_dur,v_stored,v_type,v_filter,v_dur,muxed'), [
        ('sonic-a.mjr', 'opus', None, 10.0,
         'sonic-v.mjr', 'vp8', None, 10.0,
         'mux.mkv'),
        ('streets-of-rage.pcap', 'opus', 'ssrc=4286666423', 2.0,
         'streets-of-rage.pcap', 'vp8', 'ssrc=3830765780', 2.0,
         'mux.mkv'),
    ]
)
def test_cli_mux(
        tmpdir,
        fixtures,
        a_stored, a_type, a_filter, a_dur,
        v_stored, v_type, v_filter, v_dur,
        muxed):
    dst = tmpdir.join(muxed)

    # split a
    a_src = fixtures.join(a_stored)
    a_splits = tmpdir.join('a-{0}.{1}'.format('{part:02}', 'mjr'))
    args = ['split', a_type, a_src, a_splits, '--dur', a_dur]
    if a_filter:
        args.extend(['--filter', a_filter])
    parsed = marm.cli.arg_parser.parse_args(map(str, args))
    parsed.cmd(parsed)
    a_splits = sorted(tmpdir.visit('a-*.{0}'.format('mjr')))

    # split v
    v_src = fixtures.join(v_stored)
    v_splits = tmpdir.join('v-{0}.{1}'.format('{part:02}', 'mjr'))
    args = ['split', v_type, v_src, v_splits, '--dur', v_dur]
    if v_filter:
        args.extend(['--filter', v_filter])
    parsed = marm.cli.arg_parser.parse_args(map(str, args))
    parsed.cmd(parsed)
    v_splits = sorted(tmpdir.visit('v-*.{0}'.format('mjr')))

    # mux a,v
    args = ['mux', '-f', '-ld', dst, ','.join([a_type, v_type])]
    args += a_splits
    args += v_splits
    parsed = marm.cli.arg_parser.parse_args(map(str, args))
    parsed.cmd(parsed)
    marm.FFProbe([dst.strpath])()

    # mux v,a
    args = ['mux', '-f', '-ld', dst, ','.join([v_type, a_type])]
    args.extend(sorted(tmpdir.visit('v-*.{0}'.format('mjr'))))
    args.extend(sorted(tmpdir.visit('a-*.{0}'.format('mjr'))))
    parsed = marm.cli.arg_parser.parse_args(map(str, args))
    parsed.cmd(parsed)
    marm.FFProbe([dst.strpath])()
