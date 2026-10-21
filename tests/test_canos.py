"""Análise "travada em 93%" no Windows (21/10/2026): o FFmpeg enchia o cano das mensagens
(stderr) enquanto o app só lia o cano dos dados (stdout) — os dois ficavam esperando um ao outro.
No Windows o cano é pequeno; aqui o teste escreve 2 MB de mensagens para travar em qualquer sistema."""
import sys
import threading

from revisor import media


def _run_with_timeout(fn, seconds=20):
    out = {}

    def go():
        out["v"] = fn()
    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(seconds)
    assert not t.is_alive(), "travou: as mensagens do programa não estão sendo lidas"
    return out["v"]


def test_mensagens_grandes_nao_travam_a_leitura():
    code = ("import sys; sys.stderr.write('aviso ' * 400000); sys.stderr.write('\\nSummary:\\n  I: -18.0 LUFS\\n');"
            "sys.stderr.flush(); sys.stdout.buffer.write(b'x' * 300000); sys.stdout.flush()")

    def read_all():
        proc = media._run_pipe([sys.executable, "-c", code])
        data = media._read_exact(proc.stdout, 300000)
        err, rc = media._finish_pipe(proc)
        return data, err, rc

    data, err, rc = _run_with_timeout(read_all)
    assert rc == 0 and len(data) == 300000
    assert err.rstrip().endswith("I: -18.0 LUFS")             # o fim das mensagens fica guardado
    assert media._parse_ebur128(err) == {"lufs": -18.0}


def test_parar_no_meio_nao_trava():
    # quem lê pode parar antes do fim (ex.: só os primeiros frames); o programa tem que acabar
    code = "import sys\nfor _ in range(200000): sys.stdout.write('y' * 100); sys.stderr.write('z' * 50)"

    def stop_early():
        proc = media._run_pipe([sys.executable, "-c", code])
        media._read_exact(proc.stdout, 1000)
        return media._finish_pipe(proc)

    err, rc = _run_with_timeout(stop_early)
    assert rc != 0 or err                                     # parou (cano fechado), sem travar
