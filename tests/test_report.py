from pathlib import Path

from revisor import report

HERE = Path(__file__).parent


def test_parse_real_report():
    r = report.parse(HERE / "Relatorio_tempo_2026-10-07_1032.txt")
    assert r.project == "Carlos 21:09"
    assert r.date.strftime("%d/%m/%Y %H:%M") == "07/10/2026 10:32"
    assert len(r.raw) == 7
    assert len(r.edited) == 5
    assert r.edited[2] == (50, "03 Apresentação.mp4")
    assert r.total_raw_s == 1 * 3600 + 8 * 60 + 46
    assert r.total_edited_s == 55 * 60 + 4
    assert r.usage_pct == 80.1
    assert r.discarded_s == 13 * 60 + 42
    assert sum(s for s, _ in r.edited) == r.total_edited_s


def test_find_in_folder():
    assert report.find_in_folder(HERE).name.startswith("Relatorio_tempo")


REAL = sorted((HERE / "relatorios").glob("Relatorio_tempo_*.txt"))


def test_all_real_reports_add_up():
    """Os 6 relatórios reais (set–out/2026): as linhas somam o total do próprio txt.

    O script soma as durações exatas e arredonda no fim; cada linha também vem
    arredondada. Então a soma das linhas pode diferir de 1 s por arquivo, no máximo.
    O app usa o total do txt (não recalcula)."""
    assert len(REAL) == 6
    for p in REAL:
        r = report.parse(p)
        assert r.date is not None and r.edited and r.raw, p.name
        assert abs(sum(s for s, _ in r.edited) - r.total_edited_s) <= len(r.edited), p.name
        assert abs(sum(s for s, _ in r.raw) - r.total_raw_s) <= len(r.raw), p.name
        assert r.ignored_raw is not None, p.name


def test_norm_name():
    assert report.norm_name("01 Introdução ao Direito - Parte 1-.mp4") == \
        report.norm_name("01 Introdução ao Direito - Parte 1.mp4")
    assert report.norm_name("04  Modalidades e contexto.mp4") == report.norm_name("04 Modalidades e contexto.mp4")
    # nome do macOS (acentos decompostos) = nome do txt
    import unicodedata
    assert report.norm_name(unicodedata.normalize("NFD", "03 Modelo de Fundação.mp4")) == \
        report.norm_name("03 Modelo de Fundação.mp4")


def test_match_real_folder():
    """Pasta de teste do JP × relatório de 07/10: nome mudou ('Parte 1-' → 'Parte 1')."""
    r = report.parse(HERE / "relatorios" / "Relatorio_tempo_2026-10-07_1032.txt")
    vids = [("01 Introdução ao Direito Previdenciário e ao Processo Previdenciário - Parte 1.mp4", 797.5)]
    m, w = report.match_videos(r, vids)
    assert m[0].entry == (798, "01 Introdução ao Direito Previdenciário e ao Processo Previdenciário - Parte 1-.mp4")
    assert m[0].by == "nome"
    assert sum("não está na pasta" in x for x in w) == 4     # as outras 4 aulas do lote


def test_raw_listed_as_edited():
    r = report.parse(HERE / "relatorios" / "Relatorio_tempo_2026-09-25_0708.txt")
    vids = [("01 Impacto Financeiro das decisões de TI.mp4", 1054.1),
            ("02 Case - Cloud x Infraestrutura.mp4", 742.0),
            ("03 Ferramentas de Priorização.mp4", 537.0)]
    m, w = report.match_videos(r, vids)
    assert all(x.entry for x in m)
    assert any("nome é de bruto" in x and "2026-09-18 10-41-13.mp4" in x for x in w)
