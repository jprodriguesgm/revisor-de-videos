from revisor.timecode import Rate, NTSC_2997, fmt_df, fmt_ndf, fmt_seconds, fmt_srt, parse_rate

R = Rate(NTSC_2997)


def test_frame_roundtrip():
    for f in (0, 1, 29, 30, 1798, 1799, 1800, 17982, 107892, 107891):
        assert R.frame_at(R.seconds_of(f)) == f


def test_df_known_values():
    # valores clássicos de drop frame 29,97
    assert fmt_df(R, 0) == "00:00:00;00"
    assert fmt_df(R, 1799) == "00:00:59;29"
    assert fmt_df(R, 1800) == "00:01:00;02"
    assert fmt_df(R, 17981) == "00:09:59;29"
    assert fmt_df(R, 17982) == "00:10:00;00"
    assert fmt_df(R, 107892) == "01:00:00;00"


def test_ndf_and_seconds():
    assert fmt_ndf(R, 1800) == "00:01:00:00"
    # 1 hora de vídeo 29,97 = 107892 frames; NDF fica 3,6 s atrás do relógio
    assert fmt_ndf(R, 107892) == "00:59:56:12"
    assert fmt_seconds(R, 107892) == "01:00:00"
    assert fmt_seconds(R, R.frame_at(44.5)) == "00:00:44"


def test_srt():
    assert fmt_srt(44.0) == "00:00:44,000"
    assert fmt_srt(3723.4567) == "01:02:03,457"


def test_parse_rate():
    assert parse_rate("30000/1001").fps == NTSC_2997
    assert parse_rate("29.97").fps == NTSC_2997
    assert parse_rate("25").nominal == 25
