# Revisor de Vídeos — decisões do projeto

Documento para retomar o projeto numa conversa nova. Ler este arquivo antes de tudo.

Dono: João Paulo Rodrigues (JP), Núcleo de Produção Digital, PUC Minas. Sem formação
em programação: explicar em português simples e entregar arquivos completos.

**REPOSITÓRIO PÚBLICO (open source, GPL-3.0, desde 21/10/2026).** Nada de dados reais aqui:
nunca nomes de professores, da equipe, títulos de aulas de professores identificados, vídeos, frames,
relatórios de tempo novos ou caminhos de pastas de trabalho. Nos testes e neste arquivo os nomes de
pessoas são FICTÍCIOS (trocados em 21/10). O histórico anterior, com as anotações reais, ficou no
repositório privado antigo (só arquivo; não se trabalha mais nele).

## Objetivo
App de computador para revisar rápido as aulas editadas que chegam ao núcleo.

## Vídeos
- H.264 MP4 1080p, 29,97 fps, VBR 5–10 Mbps, Rec.709 faixa limitada, áudio AAC 48 kHz.
- Duração de 50 s a 1 h (média 15–20 min). Cerca de 6 h brutas/dia → 3,5–4 h editadas/dia.
- Em pasta local. As versões com erro são apagadas depois de corrigidas (não há vídeos
  com erro para testar: os erros são fabricados em tools/make_test_videos.py).

## Máquinas
- Mac M1 (casa e trabalho) e Windows com Nvidia + Intel. Cada máquina trabalha sozinha.
- Macs do trabalho podem não deixar instalar nada / bloquear app sem assinatura: testar cedo
  e avisar a TI.
- Nada para instalar: FFmpeg, Tesseract e dicionários vão dentro do app.

## Stack
- Python + FFmpeg (análise), numpy, Pillow. Interface numa página local no navegador
  (servidor local), empacotada por sistema (Mac e Windows separados, via GitHub Actions).
- Nada sai do computador. Sem IA online (LLM só opcional e desligado).
- Repositório: só código, público. Nunca vídeos, frames de aulas nem nomes reais.

## Fluxo e telas (desenho aprovado)
Desenho: artifact "Telas do app de revisão" (claude.ai, tipo Design), 11 telas.
1. Início: pasta, professor, curso e disciplina (opcionais, com sugestões), entrega da edição
   (sugerida do txt, travada depois de salva), vinhetas, sensibilidade, juntar listas (até 8 s),
   ortografia (pt-BR + inglês + latim + lista própria), "Abrir revisão salva".
   Aviso se o nº de vídeos da pasta ≠ nº de editados no txt.
2. Análise em andamento: dá para revisar os prontos enquanto o resto analisa.
3. Resumo geral: áudio mín/máx/média, gravado/editado/aproveitamento (do txt),
   tabela por vídeo com editor (select + "Aplicar a todos"), vectorscope médio.
4a. Revisão: uma aba por vídeo, editor por vídeo, frame grande, região que mudou,
   aviso de ortografia (Ignorar/Aceitar/Comentar), grupo "lista · N itens" com passos,
   filmstrip, 5 frames vinheta→vídeo e vídeo→vinheta, forma de onda com avisos de áudio,
   comentário por frame, copiar frame+comentário, clipe de 8 s (±4 s).
   Atalhos: ← → C V G P F ⌘C, Esc.
   Zoom no frame (pedido do JP, ainda não estava no desenho): roda do mouse / pinça do
   trackpad / teclas + e −; Z alterna entre "caber na tela" e 100% (1 pixel do vídeo =
   1 pixel da tela); até 400%; arrastar para mover; mini-mapa no canto mostrando a área.
   Com zoom, o app busca o frame em resolução cheia do vídeo original (não a miniatura).
   O zoom e a posição continuam ao navegar com ← → (para comparar o mesmo texto entre
   frames). Vale também na tela cheia (F) e nos passos de uma lista.
4b. G: waveform (luma / parade RGB) + vectorscope do frame. O vectorscope geral não muda.
4c. P: conta-gotas 9×9 do vídeo original; ponto no vectorscope e na waveform; Y/Cb/Cr/RGB,
   ângulo e distância da linha de pele (123°); fixar até 4 pontos.
5. Resumo final: comentários com marcar/desmarcar e com/sem frame; copiar selecionados,
   todos com frame, todos sem frame; "Gerar SRT de cada vídeo"; horas por editor; salvar e
   exportar; gerar txt de horas.
6. Exportar e abrir revisão (pacote entre computadores).
7. Relatório do mês por editor.
Configurações: cache, pastas, análise, equipe (editores), cópia e envio ao editor
(formato do tempo, duração do bloco SRT, prefixo "CORRIGIR:", onde salvar), ortografia.

Correção pendente no desenho: alvos do vectorscope em Rec.709 (R 103°, Mg 50°, B 355°,
Cy 283°, G 230°, Yl 175°); o desenho usou Rec.601 (R 108°).

## Regras
- Timecode: guardado como nº de frame. Formatos: segundos (padrão, meio do frame),
  NDF, DF (29,97). Todo texto copiado leva "Vídeo NN · HH:MM:SS · comentário".
- SRT por vídeo: mesmo nome do vídeo + .srt; bloco de 3 s; "CORRIGIR: <comentário>".
- Identidade do vídeo = nome do arquivo + duração. Cada vídeo conta uma vez;
  revisões seguintes são "rodada 2, 3".
- Data que conta para o mês = entrega da edição (uma por projeto, a primeira entrega;
  sugerida do txt/arquivos, travada depois de salva). Dia da revisão é só histórico.
- Horas editadas contam no mês da entrega; horas gravadas no mês da gravação.
  Rótulo: "horas de vídeo editado". Relatório por professor continua na planilha Google.
- Relatório de tempo (txt "Relatorio_tempo_*.txt" na mesma pasta): o app só lê os
  números; não recalcula e não aplica a regra -D/-E (isso é da linha de produção).
- Editor marcado no app, por vídeo, com "aplicar a todos". Equipe: cada unidade cadastra a sua em
  Configurações → Equipe (o app começa sem ninguém; Início, Resumo e Revisão mostram "Cadastrar a equipe").
- Pacote de revisão: revisao.json + frames/ (só comentados) + horas.txt; só nomes, sem
  caminhos; casa por nome+duração; conflito → perguntar (manter / usar pacote / juntar).
  Cache não vai no pacote.
- Cache apagável; revisões salvas ficam em pasta separada e nunca são apagadas pelo
  "limpar cache". Salvar sozinho a cada comentário; avisar ao sair com algo pendente.
- Vinhetas iguais para todos os cursos (um par salvo nas configurações).
- Ortografia: OCR (Tesseract, modelo "por") + Hunspell pt-BR + inglês (EUA e Reino Unido)
  + latim + lista fixa do núcleo + lista própria que cresce com "Aceitar". Ver "Etapa 2".

## Transições de slide e screencast (regras do núcleo)
- Aula com slide em tela cheia: o slide ENTRA descendo em 12 frames e SAI subindo em
  12 frames. Avisar quando: entrar/sair com corte seco; durar diferente de 12 frames
  (tolerância a calibrar, ~±2); direção errada (entrada tem que ser para baixo, saída
  para cima). Direção medida pelo deslocamento vertical do conteúdo nos frames da transição.
- Entre um slide e outro: corte seco é normal (não avisar).
- Screencast: outro formato de aula — bordas/moldura diferentes, tela do computador ou
  slides, com o professor em cima (quadro sobreposto). A transição professor ↔
  screencast deve ser CORTE SECO (avisar se tiver movimento).
- Reconhecer o formato pela moldura: aprender com exemplos (2–3 aulas de screencast e
  2–3 com slide) e guardar como "modelos de moldura" nas configurações; no app, poder
  marcar um frame como "isto é screencast/slide" para ensinar um modelo novo.
- Aula de TV (TV usada como lousa interativa): editada normal. Quando a tela da TV vai
  para tela cheia, vale a mesma regra do slide (entra descendo 12f, sai subindo 12f),
  MAS dentro dela há movimento (escrita/desenho). Então:
  - reconhecer a tela da TV pelos elementos fixos da interface (bordas, barra de
    ferramentas, fundo), aprendidos com exemplos — não por "imagem parada";
  - escrita que vai aparecendo na mesma área não vira um frame marcado para cada traço:
    vira um grupo "escrita na lousa" (com passos), como as listas;
  - sem ortografia em letra de mão (OCR não lê bem).
  - Professor em quadro com a TV ao fundo: sem regra de transição (o JP confirmou que não
    é problema); a escrita na TV ao fundo também vira grupo "escrita na lousa".
  - AINDA NÃO HÁ AULA DE TV GRAVADA. Plano: construir o recurso genérico "ensinar
    formato" (marcar um frame no app como "tela da TV/screencast/slide" → vira modelo de
    moldura, sem mudar código). Até lá a escrita já é agrupada pela regra genérica
    (muitas mudanças que ficam na mesma área em pouco tempo = um grupo). A regra de
    transição da TV só liga depois que existir o modelo. Atalho: com 1 print ou 1–2 min
    de gravação de teste da tela da TV, dá para simular aulas de TV no gerador de testes.
    JP tem uma gravação BRUTA de TV de outro lugar (sem edição): usar para aprender a
    aparência da lousa e testar o agrupamento da escrita; montar com FFmpeg versões
    editadas (desce/sobe 12f certo, corte seco errado, duração errada) com gabarito.
    A tela da TV é capturada direto no OBS (imagem digital limpa): o ideal é um print
    da saída do OBS/programa da TV; foto da TV física só ajuda a identificar o programa.
    Print recebido (15/10), do núcleo onde o JP trabalhava ANTES (pode não ser igual ao
    setup atual; provável que seja a mesma origem da gravação bruta): na TV aparecem slides no modelo PUC (fundo claro com ícones
    claros, ondas azuis no alto e embaixo à direita, "PUC Minas" no canto inferior
    esquerdo); a câmera mostra o professor com a mesma TV ao fundo. Usar dois sinais:
    (1) modelo de moldura/template aprendido; (2) imagem digital SEM ruído de câmera
    (frames idênticos fora do que muda) = tela capturada (TV, screencast, slide) — vale
    mesmo quando a TV mostra algo fora do modelo. Pedir 1–2 prints em resolução cheia só
    da saída da TV (um com slide, um com escrita na lousa, se houver).
    Confirmar se o programa/TV é o mesmo do núcleo; se não for, o modelo de moldura
    precisa ser ensinado de novo com a primeira aula de TV real.
- Aviso na revisão: "02 · 00:12:40 · slide entrou com corte seco (esperado: desce em 12f)",
  com frames antes/depois.
- Entra na etapa 1 (calibragem com aulas reais).

## Tarja de nome (lower third)
- Regra do núcleo: em TODA aula (cada vídeo) a tarja com o nome do professor tem que
  aparecer no começo, com o nome ESCOLHIDO pelo professor. Erro comum: tarja com texto
  genérico ("Nome do professor").
- A tarja muda de cor e de forma (não dá para depender de um modelo visual). Então:
  procurar TEXTO que entra no começo do conteúdo (depois da vinheta), em qualquer
  posição, ler com OCR e comparar com o nome esperado (comparação tolerante a acento e
  maiúsculas). Modelos aprendidos ("ensinar formato") só como ajuda, não obrigatórios.
- Tempo: costuma entrar por volta de 8 s e durar 9 s, mas é livre (pode entrar antes ou
  depois e ser cortada se entrar slide). Janela de busca padrão: primeiros 45 s do
  conteúdo (ajustável). Sem regra de duração; no máximo um "conferir" se ficar < 2 s.
- Início ganha o campo "Nome na tarja" (sugere o nome do professor; lembra o que foi usado
  por professor nas próximas revisões).
- Avisos: "tarja não encontrada no começo deste vídeo"; "tarja com nome genérico:
  'Nome do professor'"; "nome na tarja diferente do cadastrado: 'Bruno Zantu' ×
  'Bruno Zantiu'".
- Lista de nomes genéricos proibidos editável nas configurações: "nome do professor",
  "nome do(a) professor(a)", "nome sobrenome", "professor", "nome", "título",
  "lorem ipsum", "fulano"…
- Logo PUC Minas: obrigatório, mas NÃO vira regra no app (muda de lugar; o JP confere
  pelos frames).
- Depende da etapa 2 (OCR).

## Imagem congelada (câmera travou)
- Caso real: câmera trava e a imagem do professor fica parada ~10 s.
- Detectar: num plano de câmera que vinha com movimento/ruído normal, a diferença entre
  frames cai para ~0 (frames idênticos) por ≥ 1 s, de preferência com o áudio seguindo
  (fala ativa). Refino ao frame exato do início e do fim. Aviso: "imagem congelada 10 s".
- Não conflita com slide: slide/screencast/TV são parados desde o começo do plano e são
  reconhecidos pela aparência/moldura; o congelamento acontece no meio de um plano de
  câmera. Só procurar congelamento em planos de câmera.
- Opcional: travadinhas curtas (2–10 frames repetidos) também viram aviso.
- Adicionar ao gerador de testes (congelar 10 s no meio da fala na aula A).

## Fala: takes repetidos e cortes esquecidos (etapa 2b, feita 16/10/2026)
Opção "Transcrever falas" (Settings.transcribe, liga/desliga; CLI --sem-fala). Tudo offline.
Código: revisor/speech.py (transcrição + frases + repetição) e audio.py (corte no meio da fala).

Transcrição:
- whisper.cpp (whisper-cli) + modelo ggml-small-q5_1.bin (190 MB, baixado pelo JP do
  Hugging Face — o site é bloqueado no ambiente do Claude e no shell do Mac; no app final o
  modelo vai DENTRO do pacote; o GitHub Actions consegue baixar). Procura o modelo em
  REVISOR_WHISPER_MODEL, bin/../models, revisor/data/models. whisper-cli fica em bin/.
- Áudio do conteúdo (entre as vinhetas) em pedaços de ~2 min cortados na pausa mais longa
  (plan_chunks); cada pedaço vira <cache>/<id>/speech/chunk_NNN.json. Para e continua
  (budget_s), e a barra anda por pedaço. Mudou o plano → refaz.
- Opções: -l pt, -mc 0 (sem contexto: evita "loop" e não alisa repetição), guloso
  (-bs 1 -bo 1), -sns, -dtw small (tempo por palavra), e um PROMPT com fala ao pé da
  letra ("é... a gente vai, a gente vai... Errei, vou voltar") para o Whisper não limpar
  hesitações. Qualidade em português: muito boa nas 10 aulas.
- Velocidade na máquina virtual do Mac (4 núcleos, sem GPU): ~9 s por minuto de áudio
  (2h18 de aula = ~21 min). No app nativo do M1 (Metal) deve ser bem mais rápido: medir
  na etapa 6.
- Cache e versões: SPEECH_VERSION (analyze.py) separado do ANALYSIS_VERSION: mudar a fala
  ou o áudio refaz só áudio+fala (update_audio_speech), não a imagem nem o OCR.
  Avisos refeitos sem transcrever (refresh_speech_checks) quando a lista de frases muda.
  Tipos novos em analysis["events"]: "speech_phrase" e "speech_repeat" (com miniatura);
  "speech_cut" fica nos eventos de áudio (forma de onda).

Avisos (sempre "conferir"):
1. Frase de erro (ERROR_PHRASES_DEFAULT, editável nas configurações): "retomando",
   "errei", "me enganei", "vou voltar", "deixa eu repetir", "vou gravar de novo",
   "pode cortar", "desculpa"… Palavra inteira, sem acento/maiúscula. FORA da lista por
   alarme falso nas aulas aprovadas: "de novo" sozinho, "do começo", "corta" sozinho.
   A mesma frase em até 10 s vira um aviso só.
2. Take repetido (find_repeats): as mesmas ≥ 4 palavras (≥ 18 letras, ≥ 2 de conteúdo)
   ditas duas vezes, a 2ª até 20 palavras depois do fim da 1ª e até 25 s depois. Repetir
   frase de propósito é comum ("a estratégia de penetração. A estratégia de penetração
   é…": eram 33 alarmes nas 10 aulas), então só avisa com um sinal de erro:
   reticências no fim da 1ª tentativa · palavra de erro no meio ("retomando", "opa",
   "de novo"…) · a frase inteira até o ponto, duas vezes seguidas · pausa ≥ 1,2 s com
   no máximo 3 palavras no meio. O motivo aparece no aviso. Frase de erro dentro de um
   take vira motivo do take (um aviso por erro). Loop do Whisper (3+ vezes igual) e
   repetição em silêncio são descartados.
3. Corte no meio da fala (audio.py, sem transcrição): só nos cortes do vídeo (±2
   frames), com fala dos dois lados e o som "pulando" (predição linear em 48 kHz: estalo
   isolado s1 ≥ 12 dB e erro que continua s2 ≥ 3 dB). Troca de câmera tem corte no
   vídeo mas áudio contínuo → não avisa. Em qualquer ponto da aula (sem corte do vídeo)
   dava 3–5 alarmes por minuto → desligado (CUT_ANYWHERE). Em 16 kHz quase nada aparece.
   Emendas plantadas em áudio real (tools/speech_calib.py montar + cut_diag2/3): ~55%
   achadas junto do corte. Limite: emenda sem corte no vídeo (áudio editado debaixo de
   slide/screencast) não é procurada.

Resultados (16/10/2026):
- Bruto real de "03 Modelo de Fundação" (2026-09-22 07-36-01.mp4, 13:35, 3840×1080,
  áudio estéreo) × editado: o editor tirou 7 erros (o professor diz "Retomando" ao errar).
  O app avisou os 7 (5 takes repetidos + "Vou gravar de novo"/"Retomando" + "Vou voltar").
  O 1º minuto do bruto (conversa antes de começar) também gera aviso: no bruto não há
  vinheta; no editado é cortado.
- 10 aulas aprovadas: 0 avisos de fala (antes da calibragem: 33 repetições + 9 frases).
- Corte no meio da fala: 6 avisos em 149 cortes do vídeo nas 10 aulas: Atenção e
  Transformers 00:17.2 (Rodrigo Saldanha) · Nego Bispo 04:07.4 (Renata Duarte Vasconti) ·
  AIOPs 05:07.2 e 06:11.6 (Rodrigo Paveli) · 01 Impacto Financeiro das decisões de TI 10:00.6
  (Tiago Morandi) · 03 Modelo de Fundação 04:45.4 (Bruno Zantiu).
  RESPONDIDO 19/10: o JP ouviu os 6 — todos são ritmo normal de fala, nenhum áudio cortado.
  Decisão: "corte no meio da fala" NÃO é aviso (0 de 6 certos nas aprovadas; ~55% de acerto
  nas emendas plantadas). O motor continua detectando (cache igual, sem reanalisar), mas
  summary.AUDIO_MARK_KINDS tira dos avisos e das contagens; fica em row["audio_marks"] para
  virar só uma marca discreta na forma de onda da tela de revisão (etapa 4).
  Recalibrar só com dados: medir s1/s2 desses 6 × emendas plantadas (tools/cut_diag2/3) no Mac.
- Ferramentas: tools/speech_calib.py (rapido: só vinheta+áudio+fala; mostrar; montar /
  medir: erros plantados em áudio real; bruto: bruto × editado), tools/run_one.py (um
  vídeo inteiro por comando), tools/cut_diag2.py e cut_diag3.py (corte no meio da fala).
- No Mac: cache em "_revisor_codigo/cache" no SSD (sobrevive entre conversas; a máquina
  virtual não). A máquina virtual não apaga arquivos do SSD: sobras de teste em
  "_revisor_codigo/teste_fala" e "diag" (o JP pode apagar). whisper.cpp compilado na hora
  (git clone + pip install cmake).

## Etapa 3 — telas Início, Análise e Resumo geral (18/10/2026)
Como roda: `python3 -m revisor` abre um servidor local (só 127.0.0.1, porta 8765 ou a próxima
livre) e o navegador. Sem bibliotecas novas: servidor da biblioteca padrão do Python, telas em
HTML/CSS/JS puro (revisor/ui/), fontes IBM Plex dentro do app (OFL; nada é baixado da internet).
No Mac sem o app empacotado: "Abrir Revisor.command" (precisa de python3, ffmpeg e tesseract
no computador — nos Macs do trabalho isso só vem com o app da etapa 6).

Dados do app (appdata.py), numa pasta do usuário (não precisa de administrador):
Mac "~/Library/Application Support/Revisor de Vídeos", Windows "%APPDATA%\Revisor de Vídeos"
(REVISOR_HOME troca). Dentro: configuracoes.json (vinhetas, sensibilidade, juntar, ortografia,
fala, editores, formato do tempo, SRT, histórico de professor/curso/disciplina, nome na tarja por
professor), lista_propria.txt, cache/ e revisoes/.

Revisão salva (review.py): uma por projeto = nome da pasta dos editados ("Carlos 21:09"),
em revisoes/<nome>/revisao.json, salva a cada mudança. Reabrir a mesma pasta (em qualquer
caminho) continua a mesma revisão: editor e comentários ficam; vídeo que saiu da pasta
continua guardado ("missing") para não perder comentários. Entrega da edição: sugerida pelo
txt (data do relatório) ou, sem txt, pela data mais nova dos arquivos; trava ao começar a
análise. Professor sugerido pelo nome da pasta ("Carlos 21:09" → "Carlos").

Telas (desenho aprovado, mesmas cores e fontes):
1. Início: pasta (janela do sistema — Mac AppleScript, Windows PowerShell — ou o navegador de
   pastas do próprio app quando a janela não abre), conferências da pasta (nº de vídeos e
   tempo, txt lido com bruto/editado/aproveitamento, avisos do txt, vídeo que não abre fica de
   fora), aviso de revisão já existente, professor/curso/disciplina com sugestões, entrega,
   "Nome na tarja" (novo; lembrado por professor), vinhetas (salvas uma vez), sensibilidade,
   juntar listas, ortografia, "Ouvir as falas", "Abrir revisão salva".
2. Análise: um vídeo por vez em segundo plano (jobs.py), barra por vídeo e geral, tempo que
   falta (medido; antes de medir, 4 s/min + 9 s/min com fala), Pausar/Continuar (para no meio
   do vídeo), achados por vídeo ("12 frames · 3 avisos"), vídeo com erro não para os outros.
   Vídeo já no cache fica pronto na hora.
3. Resumo geral: mínimo/máximo/média do áudio (com vídeo e tempo), números do txt, avisos da
   pasta, editor por vídeo + "Aplicar a todos" (salvo na revisão), avisos por vídeo, vectorscope
   médio de todos os vídeos com alvos Rec.709 corretos (R 103°…) e linha de pele 123° (a
   correção pendente do desenho, que usava Rec.601, está feita no app).
4. Revisão: por enquanto só uma PRÉVIA com a lista de avisos de cada vídeo (tc, tipo, texto).
   Resumo final, Relatório do mês e Configurações: telas "chega na etapa 5".

Contagens (summary.py): "frames" = textos que entraram/saíram e mudanças (lista conta 1);
cortes à parte (vão para a linha do tempo); "avisos" = transição do slide, congelada,
ortografia (some se desligada), tarja, frase de erro, take repetido, cor/brilho, áudio e vinheta.
"Corte no meio da fala" não conta (só marca na forma de onda; ver etapa 2b).
Texto da transição do slide agora diz "12f no Premiere" (≈ 9 visíveis na medida); análises
antigas do cache são corrigidas na hora de mostrar (summary.fix_note), sem reanalisar.

Proteções do servidor: só 127.0.0.1; recusa Host diferente de 127.0.0.1/localhost (outro site
não conversa com o app); POST só com JSON; arquivos só de revisor/ui/.

Testes: tests/test_app.py (revisão salva, contagens, servidor e proteções) — 69 testes passam.
tools/ui_smoke.py percorre Início → Análise → Resumo → Revisão no Chromium (Playwright) com
as aulas sintéticas: sem erro no console. Testado também: pasta sem txt, vídeo quebrado,
pausar/continuar, reabrir revisão (entrega travada), janela estreita (1000 px).

Ainda não feito (próximas etapas):
- (FEITO na etapa 4) "Juntar listas" e sensibilidade mudam sem reanalisar, pelo botão "Ajustes"
  da tela de revisão; a análise do cache é reagrupada quando a revisão pede outro intervalo.
- Não testado no Mac/Windows de verdade (janela do sistema para escolher pasta, porta,
  navegador). Testar com o app empacotado.

## Etapa 4 — tela de revisão (19/10/2026)
Arquivos: revisor/ui/revisao.js (tela), frames.py (imagens feitas na hora), rotas novas no server.py,
summary.review_items, analyze.regroup_lists. Desenho seguido: artboards Revisao, RevisaoGraficos e
RevisaoContaGotas (mesmas cores, fontes e posições).

O que a tela percorre com ← →: "itens" em ordem de tempo = frames marcados (texto entrou, texto saiu
sem par, mudança na tela/slide mudou, lista) + TODOS os avisos (imagem, texto, fala, áudio, vinheta).
Cortes NÃO são itens: viram tracinhos na linha do tempo do áudio (o hover mostra "corte"; clicar vai ao
frame). Lista = um item só, mostrando a lista inteira (último passo); os passos aparecem no canto
("Passos da lista") e dá para clicar em cada um. Shift + ← → anda 1 frame (frame "solto"; ← → voltam
para o item seguinte/anterior a partir dali). Clique na linha do tempo: vai ao ponto (gruda num item
se ele estiver a ~4 px).

Painel da direita (comentário): um comentário por frame; salva sozinho 0,7 s depois de parar de
digitar (e ao sair do campo / trocar de frame); texto vazio apaga. Guardado na revisão:
{cid, frame, text, source (chave do item ou "livre"), label, selected, with_frame, created, updated}
— selected/with_frame já preparados para o Resumo final (etapa 5). Lista "Neste vídeo · N comentários"
com ir-para e apagar.
Aviso do item atual (cartão âmbar): Ignorar (em QUALQUER aviso, não só ortografia; vale para este
vídeo, guardado em video["dismissed"] com chave estável: ortografia = palavra sem acento, outros =
tipo:frame; some da contagem das abas e do resumo geral; fica na lista apagado, com "Desfazer"),
Aceitar (só ortografia: palavra entra na lista própria e a ortografia é refeita em todos os vídeos
da revisão, sem ler o vídeo) e Comentar (preenche o comentário: "Ortografia: “pápeis” → “papéis”.").

Copiar (botão ou ⌘C/Ctrl+C fora de campo de texto): imagem PNG do frame cheio + HTML (texto + imagem)
+ texto puro, num item só da área de transferência. Texto: "Vídeo 01 · 00:00:44 · comentário"
(formato do tempo das configurações: segundos/NDF/DF — o JS repete o timecode.py). Se o navegador
recusar, copia só a imagem e depois só o texto. Testado: os 3 formatos chegam (Chromium).

V (trecho de 8 s): 4 s antes e 4 s depois, por cima do frame; para no fim; espaço toca/pausa; clicar
na barra pula; a marca âmbar é o frame. Toca o VÍDEO ORIGINAL (rota /api/media com "Range", sem
converter nada). Se o navegador não tocar (ProRes, HEVC…), o app gera um trecho em MP4 H.264
(cache/<id>/clips) e, por último, WebM (VP9/Opus). O Chromium do Playwright não tem H.264, então
aqui foi testado pelo WebM; Chrome, Safari e Edge tocam o original. ETAPA 6: o FFmpeg empacotado
precisa de um codificador H.264 (libx264, ou h264_videotoolbox no Mac / h264_mf no Windows).

Zoom: roda do mouse, pinça (trackpad no Chrome = roda com Ctrl; Safari = gesture), + − e Z
(caber ↔ 100% = 1 pixel do vídeo = 1 pixel da TELA, contando Retina); até 400%; arrastar move;
mini-mapa no canto (clique leva a área). Continua igual ao trocar de item e de vídeo. Marcações
(região, pontos) acompanham o zoom com a mesma espessura. O frame cheio é JPEG qualidade 2 na
resolução original (cache/<id>/full/), feito na hora (~0,4 s) e com cache do navegador; a miniatura
aparece antes. Os vizinhos (← →) são carregados antes.
F: tela cheia do próprio visor (Esc do navegador sai).

G: painel largo com waveform (Luma / Parade RGB, linhas 0–100%) e vectorscope do frame (alvos Rec.709
e linha de pele por cima). Waveform/parade em meia resolução (2×2 = casa com a cor 4:2:0; ~4× mais
rápido, mesma forma); vectorscope com toda a cor. ~0,03 s de cálculo + ~0,4 s para ler o frame.
P: conta-gotas. Lupa (3× por pixel, quadrado = 9×9) e mira seguem o mouse; o valor vem do SERVIDOR,
lido do YUV original (média 9×9), com até 4 frames decodificados na memória. Clique fixa até 4
pontos (numerados no frame, no vectorscope e na waveform); ao trocar de frame os pontos ficam no
mesmo lugar e são relidos (comparar o mesmo ponto entre frames). Caixa da pele: verde até 15° da
linha de pele, âmbar acima; "cor quase neutra" quando a saturação < 3%.

Rodapé: 5 frames vinheta→vídeo e vídeo→vinheta (clicar mostra o frame), tira com todos os itens
(ponto âmbar = aviso; ponto azul = comentado; "lista · N"; ignorado fica apagado) e a forma de onda
do áudio inteiro: barras âmbar onde há aviso de áudio; pontos âmbar (avisos de imagem/texto/fala),
pontos azuis (comentários), tracinhos (cortes), triângulo cinza embaixo = "corte no meio da fala"
(só marca, não é aviso); fundo escuro nas vinhetas; linha azul = posição atual.

Barra de cima: abas (uma por vídeo, com nº de avisos), editor deste vídeo + Aplicar a todos,
"Vídeo 1 de 2 · N frames marcados · N avisos" e "Ajustes" (sensibilidade e juntar listas, para a
revisão toda, SEM reanalisar: analyze.regroup_lists refaz grupos e pares entrada×saída a partir das
regiões guardadas e grava o cache).

Vídeo ainda analisando: a aba mostra o progresso e abre sozinha quando fica pronto. Vídeo que não
está neste computador (revisão aberta de outro lugar): só as miniaturas do cache, com aviso; zoom
cheio, G, P e o trecho precisam do vídeo.

Telas pequenas: os botões perdem o texto quando não cabem numa linha (fica a tecla, com dica);
painéis G/P encolhem os gráficos. Testado em 1440×900, 1280×800 e 1100×720.

Segurança das rotas novas: id do vídeo só letras/números e só vídeos da revisão aberta (nenhum
caminho vem do navegador); frames/gráficos com cache do navegador (não mudam: id = nome + duração).

Testes: tests/test_review.py (itens, listas, ignorar, reagrupar; de ponta a ponta com um vídeo
gerado: frames, gráficos, conta-gotas, Range, trecho, comentários, ignorar, ajustes, aceitar) —
73 testes passam no total. tools/ui_smoke.py agora percorre também a revisão (lista com passos,
comentário, cópia, G, P, zoom, trecho, aba 2).

Ainda não feito:
- Resumo final, SRT, pacote entre computadores, relatório do mês e configurações (etapa 5). O
  formato do tempo (segundos/NDF/DF) já é respeitado, mas só muda pelas configurações (etapa 5).
- "Ensinar formato" (marcar um frame como screencast/slide/tela da TV) — fica para depois da 5.
- Não testado em Safari/Chrome de verdade no Mac (cópia de imagem, pinça, tela cheia, tocar o
  original). Testar com o app empacotado (etapa 6) ou com o "Abrir Revisor.command" no Mac de casa.

## Etapa 5 — Resumo final, SRT, pacote, relatório do mês e configurações (19/10/2026)
Arquivos: revisor/export.py (motor, sem ler vídeo), ui/final.js (as 4 telas), rotas novas no server.py.
Desenho seguido: artboards Final, Pacote, Relatorio e Config (mesmas cores, fontes e posições).

Resumo final (#/final): todos os comentários na ordem dos vídeos e do tempo; marcar/desmarcar (e
"Todos"), "Com frame / Sem frame" por comentário (guardado na revisão: selected / with_frame).
Copiar: "selecionados, como marcado", "todos com frame", "todos sem frame" → texto puro (uma linha
"Vídeo 02 · 00:00:44 · …" cada) + HTML com as imagens (JPEG até 1280 px) num item só da área de
transferência (as imagens são buscadas dentro do ClipboardItem: o Safari exige isso). Clicar em
"Vídeo 01 · tempo" abre o vídeo na revisão.
SRT: só vídeos com comentário MARCADO; nome do vídeo + .srt, ao lado dos vídeos ou na subpasta
"Correções" (configurações); blocos de 2/3/5 s que não se sobrepõem (termina 1 ms antes do próximo);
"CORRIGIR: texto" (prefixo nas configurações; vazio = só o texto); parágrafos juntados (linha em
branco quebra o SRT); UTF-8 com BOM e fim de linha CRLF (acentos certos no Premiere nos dois sistemas).
Gerar de novo substitui. Pasta dos vídeos fora deste computador → baixa um .zip (pasta Downloads).
Horas por editor: tempo do vídeo = linha do txt de tempo quando o vídeo está nele (senão, duração
do arquivo); "Total editado" = total do txt (regra do app). "Sem editor" aparece em âmbar. "Gerar txt
de horas" baixa o txt (Downloads).
A taxa de frames de cada vídeo agora fica guardada na revisão (v["fps"]): SRT e cópia funcionam em
outro computador sem o cache.

Rodadas: vídeo novo com o MESMO nome de um que saiu da pasta (voltou corrigido, outra duração) =
rodada seguinte (round 2, 3), herda o editor; a versão antiga continua guardada com os comentários
("missing"), mas não conta nas horas.

Levar para outro computador (#/pacote; também "Abrir pacote de outro computador" na janela "Abrir
revisão salva"): exporta a PASTA "Revisão <entrega> <projeto>/" com revisao.json (sem caminhos),
frames/ (JPEG cheio de TODOS os frames comentados, para poder trocar com/sem frame no outro lado) e
horas.txt. Nunca vídeos nem cache. Abrir: escolher a pasta do pacote; mostra vídeos encontrados /
não encontrados (casa por id = nome + duração), "Localizar pasta dos vídeos"; se já existe revisão
do projeto e o conteúdo é diferente: Manter a deste computador / Usar a do pacote / Juntar as duas
(junta comentários; no mesmo frame vale o editado por último; editor marcado num lado só vale;
"ignorar" dos dois). As imagens do pacote ficam em revisoes/<projeto>/frames/ e aparecem no Resumo
final quando não há vídeo nem cache (rota cframe.jpg). Pacote adulterado: nomes viram só nome de
arquivo, ids inválidos saem, imagem fora de frames/ é ignorada.

Relatório do mês (#/relatorio): lê as revisões salvas (pasta do app + uma pasta opcional com pacotes,
ex.: Google Drive) até 2 níveis de subpasta; a mesma revisão em dois lugares conta uma vez (fica a
salva por último); a revisão aberta entra como está. Editado: mês da ENTREGA; cada vídeo conta uma vez
(mesmo id, ou mesmo nome no mesmo projeto), na primeira entrega. Gravado: brutos do txt no mês da
GRAVAÇÃO (data do nome do OBS "2026-09-21 10-36-59.mp4"); revisões antigas sem a lista de brutos
tentam reler o txt na pasta; sem isso, o total vai para a data do relatório. Cartões: gravado,
editado, aproveitamento (editado ÷ gravado do mês — pode passar de 100% quando a gravação foi no mês
anterior), vídeos; tabela por editor com parte; por curso; por semana (Sem 1 = dias 1–7 da entrega).
Exportar txt (resumo + lista) e CSV (uma linha por vídeo, ";" e vírgula decimal, UTF-8 com BOM).

Configurações (#/config, menu à esquerda rola até a seção):
- Cache: tamanho, lista por revisão (ou "Vídeos sem revisão salva") com Limpar, "Limpar todo o cache"
  (pede confirmação), limpeza automática do que não é usado há 7/15/30/60 dias (padrão 30; roda ao
  abrir o app; nunca a revisão aberta; abrir uma revisão marca o cache dela como usado). Não limpa
  vídeos de uma análise rodando.
- Pastas: cache, revisões (trocar COPIA as revisões já salvas para a nova; a antiga fica), pasta extra
  do relatório do mês.
- Análise: sensibilidade e juntar listas padrão, "Ouvir as falas" padrão, frases de erro e nomes
  genéricos da tarja (listas editáveis; mudar refaz os avisos da revisão aberta sem ler o vídeo).
- Equipe: adicionar, renomear (as revisões salvas passam a usar o nome novo), ativar/desativar.
- Cópia e envio: formato do tempo, bloco do SRT, prefixo, onde salvar; prévia do SRT e do texto.
- Ortografia: português sempre; inglês e latim liga/desliga (refaz a ortografia da revisão aberta);
  lista própria com remover e adicionar palavra OU expressão ("habeas corpus": cada palavra vale).
  Ficou de fora do desenho: "Só no curso atual" (a lista vale para todos os cursos).

Testes: tests/test_export.py (SRT, cópia, horas, rodadas, pacote ida e volta e adulterado, juntar,
relatório do mês, expressões; de ponta a ponta no servidor: resumo final, marcar, SRT, txt, pacote
exportar/inspecionar/abrir/juntar, relatório, configurações, editores, palavras, cache) — 83 testes
passam no total. tools/ui_smoke.py agora percorre também Resumo final (marcar, com/sem frame, copiar
com imagem, SRT), pacote (exportar e abrir), relatório e configurações, e as telas em 1100 px: sem
erro no console.

Ainda não feito:
- "Ensinar formato" (marcar um frame como screencast/slide/tela da TV).
- END_TOLERANCE da vinheta final ainda não está nas configurações (continua 10 frames no código).
- Não testado em Safari/Chrome de verdade no Mac (cópia com várias imagens, downloads, janelas do
  sistema para escolher pasta). Testar com o app empacotado (etapa 6) ou com o "Abrir Revisor.command".

## Etapa 6 — app empacotado para Mac e Windows (19/10/2026)
Repositório: github.com/jprodriguesgm/revisor-de-videos (PÚBLICO desde 21/10; antes privado). GitHub
conectado ao Claude pelo "Claude GitHub App".

Como monta: aba Actions → "Montar o app" → Run workflow (ou etiqueta v*). .github/workflows/montar.yml:
macos-14 (M1) e windows-2022 → testes → PyInstaller → diagnóstico → zip → Release "montagem-N"
(pré-lançamento; com etiqueta v1.2.3 vira lançamento normal). Diagnóstico de cada sistema vai na
descrição da Release e como anotação (o log do Actions não abre no ambiente do Claude).
Minutos: em repositório público o Actions é de graça. Mesmo assim só roda quando pedido, e
FFmpeg/Tesseract/Whisper/modelo ficam no cache do Actions (chave = hash de packaging/build_deps.py).
1ª montagem ~20 min; com cache ~6 min no Mac.

O que vai dentro (packaging/build_deps.py → bin/ e models/, fora do git):
- Tesseract 5.5.3 + Leptonica 1.87.0 montados do código, SEM bibliotecas de imagem (um executável de
  ~6 MB, sem dependências). Por isso o ocr.py manda as imagens em PGM (antes PNG). Sintéticos 41/41.
- whisper-cli (whisper.cpp v1.9.5): Mac com Metal (placa do M1) + Accelerate; Windows só processador
  (AVX2). GPU Nvidia no Windows (Vulkan/CUDA) fica para depois, se precisar de velocidade.
- FFmpeg 8.1.3: Mac montado do código com libx264 estática (stable) + VideoToolbox, sem bibliotecas de
  fora do sistema (GPL). Só VideoToolbox não servia: o codificador da Apple dá erro na máquina virtual
  do GitHub (-22), então o trecho de 8 s usa libx264 nos dois sistemas. Windows: build pronto do BtbN
  (GPL, com libx264, DLLs; hoje veio o 9.0.2).
- Modelo ggml-small-q5_1.bin baixado do Hugging Face pelo Actions.
Mac: deployment target 11.0, arm64. Windows: runtime do C++ estático (não pede o Visual C++ Redistributable).

App (packaging/revisor.spec, app_main.py):
- Mac: "Revisor de Videos.app" (nome do arquivo sem acento; nome mostrado "Revisor de Vídeos"),
  LSUIElement (sem ícone no Dock), assinatura ad-hoc (sem conta de desenvolvedor Apple), textos das
  permissões de pasta em português. Zip feito com ditto (guarda os links simbólicos do .app).
- Windows: pasta com "Revisor de Videos.exe" (sem janela) + "revisor-terminal.exe" (mesmo app com
  terminal, para diagnóstico/testes).
- "<app> diagnostico": confere e USA cada programa (vídeo de teste, trecho H.264, OCR, Whisper).
  "<app> analisar …" funciona como o python3 -m revisor (medir velocidade no Mac).
- Sem janela de terminal, o que o app escreve vai para revisor.log na pasta de dados.
Vida do app (revisor/life.py): instancia.json guarda a porta; abrir de novo só abre a página. A página
manda /api/ping a cada 20 s e /api/bye ao fechar; sem página (90 s depois do bye; 20 min sem ping;
5 min se o navegador nunca abriu) e sem análise rodando, o app fecha sozinho. Botão "Sair" no topo
(confirma; avisa se a análise está rodando). Página mostra "O Revisor foi fechado" quando o app sai.
Localhost sem proxy (rede da PUC pode ter proxy).
Instalação sem administrador: INSTALAR.md (Mac: xattr -dr com.apple.quarantine no Terminal, ou
botão direito → Abrir no macOS ≤ 14; Windows: Desbloquear o zip, "Executar assim mesmo").

Primeira montagem completa que passou: "montagem-4" (Releases), 19/10/2026.
Tamanhos: Mac zip 222 MB (app 296 MB); Windows zip 364 MB (pasta 638 MB).
Diagnóstico no GitHub: TUDO OK nos dois (FFmpeg, trecho H.264, OCR, Whisper com o modelo).
Mac do GitHub (macOS 14.8, máquina virtual M1): análise das 2 aulas sintéticas sem fala em 70,6 s,
41/41, 0 alarmes falsos. Whisper lá: 23 s para 2 s de áudio (carregar o modelo + sem placa de vídeo
na máquina virtual) — medir no Mac de verdade.
Minutos: com o cache, cada montagem leva ~7 min no Mac e ~8 min no Windows (ao rodar dá para escolher
só "mac" ou só "windows").
REGRA DO JP (19/10): toda correção/mudança sai SEMPRE para Mac E Windows juntos (montar com "ambos";
a Release tem os dois zips). Não montar só um sistema. Mudar packaging/build_deps.py refaz os programas (~20–30 min).

Testes portáveis: tests/conftest.py (FFmpeg do app; sem libx264 usa MPEG-4; pasta "Ana 19-10" no
Windows porque ":" não pode), tests/test_life.py. tools/make_test_videos.py usa Arial no Mac/Windows.
Testado no Linux: app montado pelo PyInstaller → análise 41/41 e tools/ui_smoke.py --sair sem erro.

Primeiro teste do JP no Mac de casa (19/10/2026, montagem-4, Safari):
- Instalação: zip baixado da Release, xattr no Terminal → abriu. Análise de 3 aulas reais (33 min, com fala)
  em ~5–6 min (≈ 10 s por minuto de aula). Fala: 0 avisos (aulas aprovadas). V (trecho de 8 s) e
  "Copiar frame + comentário" funcionam no Safari.
- Corrigido depois do teste (montagem-7):
  · "null" no cartão de progresso (replaceChildren com null no Safari/Chromium) → app.js ignora null.
  · Miniaturas com "?" enquanto a análise rodava → a imagem que falha tenta de novo sozinha (3 vezes).
  · Tarja com professor "Varios": procurava "varios" → "Vários/Diversos/Todos…" valem como sem nome;
    nome cadastrado que não aparece agora mostra o nome lido ("'Léo Rinaldi' × 'Rodrigo Paveli'").
  · Pedido do JP: faixa ROXA na linha do tempo onde há slide em tela cheia (summary.slide_spans: corte
    "entra" → "sai"; corte seco com aviso também), legenda "N slides na tela", hover "slide 3 de 9".
  · Pedido do JP: "texto entrou" mostrava o lettering no meio da animação (borrado/deslizando) →
    video.settle_frame: até 4 s depois, primeiro frame com 10 frames seguidos sem mudança na região
    (limiar 12% do maior movimento). OCR lê a partir desse frame. ANALYSIS_VERSION 9.
  · Imagem congelada: começo procurado de 1,5 s antes da passada leve (no Mac do GitHub achava ~1 s
    depois). ANALYSIS_VERSION 10. No Mac do GitHub ainda sai +7 frames no sintético (x264 diferente;
    40/41 na conta do evaluate) — irrelevante na prática, aqui 41/41.
  · /api/log.txt (fim do revisor.log) e "timings" na rota do vídeo, para diagnosticar no Mac do JP
    (a pasta Library não pode ser aberta pelo Claude). O Claude acompanha pelo navegador embutido
    (http://127.0.0.1:8765, liberado pelo JP) e por prints do Safari.
- "texto saiu" logo depois da vinheta de abertura (00:00:06, J.L. Moreno/AIOPs): provável fim da animação da
  vinheta → alarme falso a calibrar.
- Testado depois pelo JP (montagem-7): abrir revisão salva ok, Sair ok; "a versão do Mac me parece perfeita".
- Pedido do JP: "Navegar slides" (botão na barra da revisão, liga/desliga, vale para todas as revisões —
  configuração nav_slides): cada slide em tela cheia vira item navegável com ← → ("slide 3 de 9"), frame
  depois da transição (+15f) ou do corte seco slide→slide (+2f); risca roxa embaixo da miniatura.
  Para conferir português/formatação que passou batido (a ortografia automática já lê cada slide).
- Mac do trabalho (M1 Max, macOS 13.1, 20/10): a montagem-9 NÃO abria — o pip no Mac 14 do GitHub escolhia o
  numpy "macosx_14_0" (Accelerate, só macOS 14+). Corrigido na montagem-10: o workflow troca pelo numpy
  "macosx_11_0" e packaging/check_macos_min.py confere o "minos" dos 100 Mach-O do .app (falha se > 11.0).
  Montagem-10: maior macOS mínimo 11.0; Mac e Windows TUDO OK; sintéticos 41/41.
- 21/10: o JP está usando no dia a dia ("acho quase tudo maravilhoso, acho mais erros mais rápido") e tem
  novas sugestões — tratar numa conversa nova (ler este arquivo primeiro).
- Faltou testar: SRT no Premiere, Windows real.

Ainda não feito / a medir no Mac do JP:
- Velocidade nativa no M1 (análise por minuto de aula; fala com Metal).
- Janelas do sistema para escolher pasta (osascript) a partir do app sem Dock; permissões de pasta.
- Safari/Chrome de verdade: cópia com imagens, downloads, tocar o original.
- Mac do trabalho: se a TI bloqueia app sem assinatura mesmo com xattr. Se bloquear: conta de
  desenvolvedor Apple (US$ 99/ano) para assinar e notarizar.
- Windows real (tem Parallels no Mac de casa: dá para testar lá).

## Pedidos do JP depois do uso no dia a dia (21/10/2026)
Feitos numa conversa só (o JP pediu a dificuldade antes; a fila foi a única "média/difícil").
1. ↑ ↓ na revisão: de corte em corte (os tracinhos da linha do tempo) — o JP dá uma olhada em cada
   emenda. Mostra o 1º frame depois do corte; HUD diz "corte 3 de 41"; botões ↑ ↓ na barra de ferramentas.
2. "Próxima aula" (botão azul no fim da barra de cima, tecla N): vídeo seguinte; na última aula vira
   "Próxima pasta" (a seguinte da fila, video_view.next_folder) ou "Resumo final" (sem fila).
3. Barra de abas: não volta mais para o começo. Guarda a posição entre as telas (RV.tabsScroll) e
   desliza até deixar a aula aberta no meio; o polling (vídeo analisando) não mexe nela.
4. Trecho (V) com duração escolhida: caixa dentro do trecho "N s antes e depois" (1, 2, 3, 4, 6, 8, 10,
   15; frames.CLIP_HALF_CHOICES), lembrada nas configurações (clip_half_s, padrão 4). Trecho em MP4/WebM
   do cache ganha o "h" no nome (c0000360_020.mp4); o de 4 s continua com o nome antigo.
5. Medidor de áudio em tempo real dentro do trecho (Web Audio, AnalyserNode): pico em dBFS de −60 a 0,
   sobe na hora e desce 24 dB/s, marca de pico que segura 1,5 s, "pico" = maior valor do trecho, "0 dB"
   acende se encostar no máximo. Verde até −6, âmbar até −1, vermelho acima. Mono (o navegador soma os
   canais; as aulas são mono). Só liga quando o áudio do navegador está funcionando — se não, o trecho
   toca normal sem o medidor. Conferido: tom de −18 dBFS lido como −17,7.
6. FILA DE PASTAS (o mais importante): antes o app tinha UMA revisão aberta e UMA análise; abrir outra
   pasta parava a análise (por isso outro navegador mostrava a mesma aula: é o mesmo app). Agora:
   - App.queue (server.py): uma análise por vez, uma pasta depois da outra, em segundo plano. Trocar a
     revisão aberta NÃO para a análise. App.job virou propriedade = análise da revisão aberta (pode estar
     "idle" = esperando a vez).
   - Início: com outra pasta analisando, o botão vira "Adicionar à fila" (a revisão aberta não muda; o
     formulário limpa para a próxima pasta) e aparece o cartão "Fila de análise" embaixo.
   - Cartão da fila (Início e Análise): situação de cada pasta, Abrir, "Analisar agora" (passa na frente;
     a que estava rodando volta para a fila logo depois — vídeos prontos ficam no cache), × tirar da fila
     (rodando: confirma; a revisão salva não muda). Pausar a análise segura a fila junto.
   - Topo: "Fila 2/3" (prontas/total), detalhe ao passar o mouse; até 1400 px, Relatório e Configurações
     ficam só com o ícone para as etapas não quebrarem a linha.
   - Abrir revisão salva com outra pasta analisando: entra no fim da fila; vídeos com análise anterior no
     cache abrem na hora. Reabrir pasta já analisada nesta sessão: se a pasta mudou (vídeo corrigido,
     rodada 2), analisa de novo; senão só troca a revisão.
   - fila.json (pasta de dados): pastas que não terminaram. Ao abrir o app de novo, o Início/Análise
     mostram "Da última vez ficaram na fila…" com Continuar a fila / Descartar (não começa sozinho).
   - Limpeza do cache nunca apaga vídeos de pastas na fila; "Sair" avisa que a fila volta depois.
   - Rotas: GET /api/queue; POST /api/queue/now, /api/queue/remove, /api/queue/restore;
     /api/start devolve {queued, position, running}; /api/reviews/open devolve {queued, ready_n}.
Testes: tests/test_fila.py (fila em ordem e nunca duas ao mesmo tempo, analisar agora, fila que ficou,
trecho com duração, reabrir com vídeo novo) — 100 testes passam. tools/ui_novidades.py percorre no
Chromium: Adicionar à fila, ↑ ↓, trecho 2 s, medidor, N, Próxima pasta, 12 abas centralizadas
(1100 px) — sem erro no console; tools/ui_smoke.py continua sem erro.
Limite: o medidor só existe durante o trecho (é o único momento em que o app toca som).
Correção depois do 1º teste do JP (montagem-12): voltando ao Início com uma pasta analisando, o formulário
ainda tinha a MESMA pasta e o botão ficava "Analisar vídeos" (o JP achou que a fila não existia). Agora o
formulário vem vazio ("Adicionar à fila"); escolher a pasta que já analisa mostra "Ver a análise" (não
recomeça), com um botão pequeno "Recomeçar a análise desta pasta com estas escolhas".
Montagem-11 (21/10): Mac e Windows TUDO OK no diagnóstico; sintéticos no Mac do GitHub 40/41 (o mesmo
+7 frames da imagem congelada de antes, x264 diferente). Falta o JP testar a fila no Mac.

## Comentário geral do vídeo (21/10/2026, pedido do JP)
- Um por vídeo, sem tempo ("aumentar o áudio geral", "mexer na cor da pele"): caixa "Comentário geral do
  vídeo" no painel da direita da revisão (salva sozinho 0,7 s depois de parar de digitar; vazio apaga;
  botão Copiar → "Vídeo 01 · Geral · texto"). Rota POST /api/general {id, text}.
- Guardado na revisão em video["general"] = {text, selected, created, updated} (review.general_of,
  review.comment_total contam o geral junto).
- Resumo final: vem primeiro em cada vídeo (export.comment_rows: frame None, tc "Geral", cid "g<id>",
  with_frame sempre falso); marcar/desmarcar pelo final/mark (o "Todos" pega também).
- SRT: bloco no começo do vídeo (frame 0) com "CORRIGIR: (geral) texto"; desmarcado não entra.
- Pacote: vai no revisao.json (limpo em _clean_video); juntar → vale o mais recente.
- Testes: tests/test_geral.py.
- Junto: render() do app.js agora desenha uma tela de cada vez (trocar de tela muito rápido misturava
  duas telas e deixava os atalhos da antiga ligados — visto nas capturas).

## Pedidos do JP de 22/10/2026
1. ANALISAR DE NOVO. Problema: vídeo que volta para a 2ª revisão com o MESMO nome e a MESMA duração tem o
   mesmo id (nome + duração) e abria a análise antiga do cache ("Análise anterior"), com frames da versão
   com erro. Agora:
   - analysis.json guarda "source": {"size"} (tamanho do arquivo). analyze.is_stale: tamanho diferente =
     outro arquivo → refaz do zero (apaga cache/<id>/ inteiro: miniaturas, frames cheios, trechos, fala).
     Análise antiga sem "source" ganha o campo na próxima leitura (não dá para saber se mudou antes).
   - Botão "Analisar de novo": ↻ no fim de cada linha pronta da tela de Análise e seção no fim de
     "Ajustes" na revisão; janela com "Só o vídeo NN" / "Todos os vídeos da pasta". Rota POST
     /api/reanalyze {id | "all"}: grava a marca cache/<id>/REANALISAR (analyze.mark_reanalyze; sobrevive a
     fechar o app e à fila) e põe a pasta na frente da fila (se outra pasta analisa, é a próxima).
   - Enquanto a marca existe ou o arquivo é outro, App.load_analysis devolve None (aba "analisando").
   - Mesmo id → NÃO muda editor, comentários, rodada, entrega nem as horas do mês (conta uma vez).
   - Imagens com versão no endereço (&v=analyzed_at, video_view "ver" e final rows "ver"): o navegador
     não mostra a imagem guardada da versão anterior. FrameService.forget(id) limpa a memória do vídeo.
   - Fila: open_saved compara (id, tamanho) para saber se a pasta mudou. jobs.snapshot "cached" só
     quando a análise é deste arquivo (analyze.cache_ok).
   - Testes: tests/test_reanalisar.py.
2. Vectorscope com quadrados coloridos (R, Mg, B, Cy, G, Yl; SCOPE_TARGET_COLORS em app.js) no resumo
   geral, em G e no conta-gotas (todos usam scopeOverlay).
3. Trello (imagem + comentário juntos): o JP decidiu deixar PARA DEPOIS. Ideia preferida: botão "Copiar
   para o Trello" com o texto escrito numa faixa embaixo do frame (e/ou colagem de vários frames com
   legenda, como a ferramenta "conferevideo" do antigo chefe dele, cujo código o Claude não conseguiu abrir).
4. VULKAN NO WINDOWS (feito 22/10, pedido do JP: "não gosto de usar só o processador do Windows"):
   - Leitura do vídeo já usava a placa (-hwaccel auto no Windows, videotoolbox no Mac; media.hwaccel_args).
     OCR (Tesseract) continua no processador (não há placa de vídeo útil para ele).
   - Fala: o app do Windows leva DOIS whisper: whisper-cli-vulkan.exe (-DGGML_VULKAN=ON) e whisper-cli.exe
     (processador, reserva). build_deps.py monta o do Vulkan com o Vulkan SDK (passo "Vulkan SDK (Windows)"
     no montar.yml, LunarG 1.4.313.2 em C:\VulkanSDK\sdk; só quando o cache dos programas muda).
   - speech.transcribe_chunk: Vulkan primeiro; se não abrir/falhar → refaz o pedaço no processador e segue no
     processador até fechar o app (speech._gpu_problem). Sem vulkan-1.dll no System32 → nem tenta. SetErrorMode
     no Windows: sem janelas de erro do sistema se o programa não abrir/travar.
   - Escolha da placa: o whisper 1.9.5 pega a 1ª placa do Vulkan, que pode ser a Intel integrada. Lê das
     mensagens "found GPU device i: VulkanN (type: t, cnt: c)" (1 = dedicada, 2 = integrada); se caiu na
     integrada, o próximo pedaço tenta -dev 1, 2… e fica na dedicada (speech._gpu). Sem -np agora (as
     mensagens dizem onde rodou). O nome da placa vem do Windows (Win32_VideoController), só para mostrar.
   - Cada pedaço guarda backend/gpu/gpu_type; analysis["speech"] também. Tela de Análise: "Falas: na placa
     de vídeo (NVIDIA …)" ou "Falas: no processador · a placa de vídeo não funcionou" (jobs.snapshot
     speech_engine = speech.engine_view()). Diagnóstico: linha "Whisper VK" (não é erro sem placa: o
     GitHub não tem placa de vídeo). REVISOR_WHISPER_GPU=off desliga o Vulkan.
   - Achado: no whisper-cli 1.9.5 o flash attention vem LIGADO e desliga o -dtw ("dtw_token_timestamps is
     not supported with flash_attn"). Sempre foi assim (calibragem da fala feita assim). Não mudado.
   - Testado aqui com o Vulkan por software (lavapipe, GGML_VK_VISIBLE_DEVICES=0) e com programas falsos
     (tests/test_gpu_fala.py). FALTA: medir no Windows do JP com a Nvidia (tempo por minuto de aula).
- tools/ui_smoke.py precisa de um REVISOR_HOME com a equipe "Mônica" (configuracoes.json com
  {"editors":[{"name":"Mônica","active":true}]}) e de um Relatorio_tempo_*.txt na pasta das aulas.

## Correções do Windows (21/10/2026, 1º uso do JP no Windows com a 1.0.0)
- Análise "travada em 93%": 93% é o fim do OCR e o começo da leitura do áudio. O FFmpeg manda o áudio
  por um cano (stdout) e as mensagens por outro (stderr); o app só lia as mensagens no fim. No Windows o
  cano é pequeno: enchia, o FFmpeg parava e o app esperava para sempre (no Mac o cano é maior). Agora
  media._run_pipe lê as mensagens o tempo todo numa linha separada (_finish_pipe fecha tudo), em todos os
  leitores (iter_yuv, iter_alpha, iter_audio) + "-nostats" no áudio. tests/test_canos.py reproduz o
  travamento (2 MB de mensagens) — com o código antigo o teste trava; com o novo passa.
  A barra também anda durante a leitura do áudio (93→95%), em vez de ficar parada.
- Janela de escolher pasta abria ATRÁS do navegador: o app não tem janela própria e o Windows não deixa
  programa "de fundo" passar na frente. dialogs.py: janelinha invisível sempre no topo, dona da janela de
  escolha, + AttachThreadInput/SetForegroundWindow (Add-Type, com try/catch); script enviado por
  -EncodedCommand. A montagem do Windows confere a sintaxe e compila o Add-Type
  (packaging/check_dialog_ps.py). E em todo sistema a página mostra "Escolha a pasta na janela que abriu"
  com "Usar o navegador do app" enquanto a janela do sistema está aberta.

## Open source, versões e distribuição (21/10/2026)
- O JP abriu o código (a TI da PUC aprovou em nome dele) para a TI conferir e para as equipes de outras
  2 unidades baixarem direto do GitHub. Licença GPL-3.0-or-later (o FFmpeg com libx264 dentro do app é
  GPL); licenças de cada peça em LICENCAS-DE-TERCEIROS.md.
- Repositório público novo, sem histórico; o privado antigo (com notas e nomes reais) virou arquivo.
- Dois tipos de Release: "Montagem N (teste)" = pré-lançamento (Run workflow; o JP testa primeiro) e
  "Revisor de Vídeos X.Y.Z" = oficial (campo "Versão oficial" do Run workflow ou etiqueta vX.Y.Z; o
  workflow grava o número em revisor/__version__ e cria a etiqueta). 1.0.0 saiu em 21/10/2026.
- Zips com nome fixo (Revisor-de-Videos-mac.zip / -windows.zip): links permanentes
  github.com/jprodriguesgm/revisor-de-videos/releases/latest/download/Revisor-de-Videos-mac.zip (e -windows).
- A versão do app aparece no fim do menu de Configurações.
- GUIA.md: tutorial com imagens (baixar pelo GitHub, instalar, atualizar, cadastrar equipe, fluxo do dia,
  todas as funções e atalhos). Imagens em docs/guia/, feitas só com as aulas sintéticas.
- Equipe padrão vazia (cada unidade tem a sua).

## Tamanho do app (estimativa)
| Parte | Aprox. |
|---|---|
| Python + numpy + Pillow | 60–100 MB |
| FFmpeg + FFprobe (versão enxuta, só o necessário) | 20–40 MB (completa: até 150 MB) |
| Tesseract + por (só português; "eng" não é usado) | 20–40 MB |
| Dicionários pt-BR, inglês (EUA/RU), latim | ≈ 9 MB |
| Telas | < 5 MB |
| Total sem transcrição | ≈ 150–300 MB |
| Whisper "small" q5_1 (escolhido; arquivo de 190 MB) + whisper-cli | + ≈ 200 MB |
| Total com transcrição | ≈ 350–500 MB (com "medium/turbo": até ~1,8 GB) |
Decisões: FFmpeg enxuto; Whisper "small" comprimido; modelo DENTRO do app (baixar na
primeira vez pode ser bloqueado na rede da PUC). Download compactado ≈ 40–60% disso;
Windows um pouco maior. Números exatos saem na etapa 6. Cache: poucos MB por aula.

## Testes com aulas reais
- As aulas estão no Google Drive (Google Drive para computador instalado no Mac).
  Não usar link nem conector do Drive para baixar vídeos: pedir acesso à pasta do Drive
  no Mac e rodar a análise lá; vídeos não saem do computador. Se não der, trazer só
  poucas aulas escolhidas, com ok do JP.
- Escolher 8–10 aulas variadas (professores diferentes, slides, listas, aberto/close,
  2–3 de screencast, 2–3 com slide em tela cheia, (TV: ainda não existe; ver acima),
  uma longa de 40 min–1 h, uma bem curta). Pastas antes de 02/09 e pasta de saída = já
  editadas e corrigidas → servem para medir alarmes falsos. Acervo inteiro só no fim,
  como teste de resistência.

## Calibragem com aulas reais (15/10/2026)
Pasta no Mac de casa: SSD externo "/Volumes/SSD Mac/Vídeos App analise", separada por
tipo: Screencast (3), TP - Lettering (3), TP - Slide (3), TP - Slide e Lettering (1),
Vinhetas (Entrada.mov, Saida.mov). 10 aulas já corrigidas, 2h18 no total. Sem txt de
tempo nesta rodada (o JP vai mandar exemplos depois).
Como rodou: shell Linux do app do Claude no Mac (máquina virtual, 4 núcleos, sem
aceleração de vídeo). Processos em segundo plano não sobrevivem entre comandos (limite de
180 s por comando): uma ou duas aulas por comando. Código levado como .tgz para
"_revisor_codigo/" na pasta do JP (lá também ficam as folhas de contato "folhas/";
o JP pode apagar essa pasta). Miniaturas vistas na nuvem só com ok do JP, apagadas depois.

O que as aulas reais mostraram e o que mudou:
- Vídeos: H.264 1080p 29,97, áudio AAC MONO 48 kHz, 4,2–5,1 Mbps.
- Vinhetas: ProRes 4444 COM transparência. A inicial (181 f) some por cima da aula nos
  últimos ~20 f; a final (121 f) começa transparente e aparece por cima da aula. Os frames
  do fade não batem com o arquivo nem nos pixels opacos → a comparação usa só frames com
  ≥ 99% da tela coberta (vinheta.py). Conteúdo começa onde a inicial fica < 50% visível
  (frame 168) e acaba onde a final passa de 50%. Resultado: achadas nas 10 aulas.
- Áudio: o FFmpeg 4.x não aceita "framelog=quiet" (o áudio dava −120 dB). Trocado por
  "framelog=verbose"; e agora, se o áudio não for lido, dá erro em vez de −120 dB.
- Áudio com gate/redutor de ruído: entre frases vai a silêncio digital DESCENDO aos poucos.
  "gap" agora só quando os 10 ms colados no silêncio ainda estão em volume de fala
  (> −40 dB antes, > −30 dB depois). Era 830 avisos falsos → 1.
- Ruído de fundo: com o gate, o ruído medido nas pausas sobe e desce ±10 dB o tempo todo.
  Agora precisa ficar 4 trechos de 5 s estáveis antes e depois (perto do fim vale o que
  sobra). Era 134 → 3. Mudança de volume: janelas de 3 s (era 1,5 s). Era 15 → 0.
- Cor/brilho: alarme a ~1 s dos cortes (começo da transição do slide) e junto de texto
  com faixa escura → ignorados a ±2 s de corte e a ±1 s de texto. Era 18 → 0.
- Texto: entrada e saída na mesma região viram um item só (a saída vira a duração
  "na tela por X s"; saída sem entrada continua aparecendo).
- Transição do slide (transitions.py, NOVO): para cada corte, mede a trajetória vertical
  do slide frame a frame (slide deslocado por cima da câmera). Nas 4 aulas com slide:
  64 de 64 transições = entra vindo de cima, sai indo para cima, 9 frames de movimento
  visível (do último frame parado ao primeiro parado, precisão ~4 px). PADRÃO = 9 ± 2.
  O JP disse 12 frames: os 1–2 primeiros/últimos frames da transição de 12f do Premiere
  quase não se movem (suavização) → 9 visíveis. CONFIRMADO pelo JP (15/10): é 12f no
  Premiere. Na tela, mostrar "12f no Premiere" e usar 9 visíveis na medida.
  Corte seco câmera↔slide só é avisado se o slide tem a mesma moldura (bordas) dos
  slides que entraram com movimento NESTA aula; em aula de screencast (só corte seco)
  não avisa. Slide→slide com corte seco: normal. 0 alarmes nas 10 aulas.
- Imagem congelada (video.py, NOVO): plano de câmera (diferença típica ≥ 0,15) em que
  tudo para (< 0,05 no quadro e < 0,3 na zona do professor) por ≥ 1 s, longe dos cortes.
  Refino ao frame (quadro-chave do H.264 no meio do congelamento muda até ~0,1). O pulo
  da imagem quando a câmera volta não vira "corte". 0 alarmes nas 10 aulas.
- Gerador de testes: aula A agora tem câmera congelada 10 s (9–19 s), slide saindo para
  baixo (50 s), slide entrando com corte seco (100 s) e saindo rápido (106 s); aula B tem
  as transições certas. Trajetória do slide copiada das aulas reais.
  Resultado sintético: 34/34 acertos, 0 alarmes falsos.

Relatórios de tempo (6 txt reais de 23/09 a 09/10, em tests/relatorios/): todos lidos.
- A soma das linhas pode diferir do total em ~1 s por arquivo (o script arredonda no fim):
  o app usa o total do txt.
- O mesmo vídeo pode ter outro nome no txt ("… Parte 1-.mp4" no txt, "… Parte 1.mp4" na
  pasta) e espaço duplo ("04  Modalidades"); no Mac os acentos vêm decompostos.
  report.match_videos casa por nome tolerante (sem acento/maiúscula/espaço duplo/"-" no
  fim) e, se não achar, pela duração (±1 s, só se uma linha bater). Testado no Mac com
  3 lotes: todos casaram pelo nome.
- Achado: em 2 relatórios (25/09 e 28/09) um BRUTO aparece entre os editados
  ("2026-09-18 10-41-13.mp4", 0:16; "2026-09-18 13-19-26.mp4", 0:44) — provavelmente o
  arquivo de teste do começo da gravação foi parar na pasta Saida. O txt conta esse tempo
  como editado. O app avisa: "O relatório conta '…' como editado, mas o nome é de bruto."
  (não recalcula nada; quem corrige é a linha de produção).
- Nem toda aula tem txt: o relatório começou em set/2026. Sem txt, a análise funciona
  e só ficam vazios gravado/editado/aproveitamento.
- Também lê a linha "Ignorados por terminarem em -D ou -E" (só informação).

Números nas 10 aulas (sensibilidade 55): 232 itens = 129 cortes (informativos: troca de
plano, câmera↔slide, jump cut), 98 textos (87 entradas + 11 saídas sem par),
1 aviso de vinheta (depois tolerado), 4 de áudio (depois 0), 0 de slide, 0 de congelamento. Antes da calibragem:
~1.300 (quase tudo áudio falso).
Velocidade: 3,0 s por minuto de aula na máquina virtual do Mac M1 (sem aceleração de
vídeo; 75% é a passada leve). 6 h de bruto/dia → ~18 min. O app nativo no M1, com
VideoToolbox, deve ser mais rápido (medir na etapa 6).

Para o JP conferir (aulas corrigidas, então provavelmente alarme falso — ouvir/olhar):
- (RESPONDIDO 15/10) "AIOPs": vinheta final com 6 de 121 frames a menos (fim parado) →
  o JP disse que dá para tolerar. Tolerância padrão: até 10 frames a menos no fim da
  vinheta final (END_TOLERANCE em vinheta.py; vai para as configurações).
- (RESPONDIDO 15/10) Áudio: AIOPs 03:47 ruído cai 10 dB; Nego Bispo 03:22 cai 12 dB e
  11:05 cai 9 dB; Atenção e Transformers 12:30 "áudio volta de repente" → o JP ouviu
  (caixa no máximo): nada; o último é o ritmo de fala do professor. Todas as 10 aulas
  foram aprovadas pelo revisor anterior. Ajuste: ruído de fundo só a partir de 13 dB
  (NOISE_DB) e "fala começa cortada" só acima de −18 dB nos primeiros 10 ms
  (GAP_START_DB). Resultado: 0 avisos de áudio nas 10 aulas; sintéticos continuam 34/34.
Visto nas folhas e ainda não resolvido:
- Texto que entra por cima do professor (ex.: "Sociograma" embaixo, em Moreno 06:2x;
  frase em faixa escura que vai aparecendo palavra por palavra em Nego Bispo) às vezes
  só aparece como saída/corte, ou nem aparece. A etapa 2 (OCR) pode ajudar.
- A tarja de nome e o título (lettering) entram como text_in no começo: base boa para a
  regra da tarja (etapa 2).
- Mudança de slide dentro do screencast aparece como text_in/out de área grande: na
  tela, chamar de "slide mudou".
- Cortes: 129 em 10 aulas. Na interface, deixar na filmstrip/linha do tempo, não na
  lista de avisos (decidir nas telas).

## Etapa 2 — texto na tela, ortografia e tarja (15/10/2026)
Como funciona (revisor/ocr.py, spell.py, nametag.py):
- O OCR NÃO lê o vídeo inteiro. Lê: (a) cada texto que entrou (1 s depois da entrada e de
  novo no fim, antes de sair — texto que aparece palavra por palavra só fica inteiro no
  fim), (b) texto que saiu sem ter sido visto entrando, (c) slide que mudou, (d) o frame
  logo depois de cada corte (slide em tela cheia), e (e) uma VARREDURA do começo do
  conteúdo: 3 frames/s nos primeiros 45 s, para a tarja (+ 1 frame/s lido inteiro, como
  rede de segurança).
- Por que a varredura: nas 10 aulas a etapa 1 não viu NENHUMA tarja (entra animada, fica
  3–8 s, às vezes por cima da zona do professor). E a página inteira no Tesseract não
  acha texto claro em caixa colorida. Então a varredura acha "linhas com cara de texto"
  (muitas bordas de letra lado a lado, em meia resolução; mancha alta ou rala é cortada
  em faixas de linha), recorta do frame cheio e faz 4 versões preto-no-branco de cada
  caixa: justa + limiar global (Otsu) e folgada + limiar local, cada uma nas duas
  polaridades; apaga o fundo escuro em volta e as bordas finas da caixa; empilha tudo de
  3 s de vídeo numa imagem só, chama o Tesseract uma vez (psm 11) e, por caixa, fica a
  versão lida com mais letras confiáveis. Nenhum preparo único servia para as 10 tarjas
  (caixa clara sobre fundo escuro, texto claro em caixa colorida, letra fina…).
- Modelo "por" sozinho: o "por+eng" perdia acentos ("Familia", "Salario") — testado.
  O "por" lê bem os termos em inglês. Modelo tessdata_fast (o "best" não ficou melhor e
  é 2–3× mais lento).
- Ortografia: palavra certa se pt_BR, en_US, en_GB ou latim aceitar, ou se estiver na
  lista fixa (data/dict/palavras_nucleo.txt) ou na lista própria. O português manda:
  "familia" (o inglês/latim aceitam) é avisada porque em português leva acento.
  Antes de avisar, a palavra é RELIDA ampliada; se a releitura der palavra certa, foi
  engano do OCR. Não checa: siglas (até 6 maiúsculas), nomes com maiúscula no meio
  (AIOps), palavras com número (Word2Vec), sem vogal ("chs"), endereços de site,
  leituras da varredura da tarja (slide pequeno lido por ela vira lixo),
  palavras cortadas na borda, palavrinha solta de até 4 letras numa linha só, palavra
  que aparece inteira em outra leitura do mesmo vídeo ("finan" → "financeiro": era
  texto animado lido pela metade) e palavra com maiúscula no meio da frase (nome
  próprio), a não ser que o problema seja acento. Cada palavra é avisada uma vez por vídeo
  ("aparece 3 vezes"). Sugestões rápidas próprias (acento, trocas comuns do português,
  uma letra) — as do Hunspell levavam 7 s por palavra.
- Tarja: compara o "Nome na tarja" com as leituras dos primeiros 45 s, sem diferença de
  maiúsculas; vale a MELHOR leitura (a animação dá leituras pela metade).
  Resultados: ok · acento diferente (conferir) · diferente ("Bruno Zantiu" × "Bruno Zantu")
  · genérico (lista nas configurações) · não achada. Sem nome cadastrado, mostra o nome
  que parece estar na tarja (texto com cara de nome, de preferência na metade de baixo,
  ignorando o logo "PUC Minas" e textos que ficam na tela o tempo todo).
  Tempo na tela = do primeiro ao último frame da varredura em que o nome foi lido;
  < 2 s → "conferir".
- Tudo guardado no cache (leituras com posição e confiança). Ortografia e tarja são
  refeitas sem ler o vídeo quando a lista própria ou o nome mudam
  (analyze.refresh_text_checks). Avisos novos: tipos "spelling" e "name_tag".

Resultado nas 10 aulas reais (todas já aprovadas):
- Tarja encontrada em 10 de 10, todas entre 7 e 9 s do vídeo: Felipe Arantes (Moreno),
  Renata Duarte Vasconti (Nego Bispo), Rodrigo Saldanha (Atenção), Léo Rinaldi (VP e VPL;
  Pricing), Rodrigo Paveli (AIOps), Bruno Zantiu (Modelo de Fundação), Carlos Tavião
  (Previdenciário), Marco Lacerda (Design arquitetural), Tiago Morandi (Impacto
  Financeiro). O JP confirmou (15/10) que Design (8 s) e Impacto (9 s) têm tarja — na
  1ª versão não eram achadas; o preparo em 4 versões resolveu.
  Com o nome cadastrado de cada professor: 10 de 10 "tarja ok", nenhum "conferir".
  Testes de nome errado: "Bruno Zantu" → diferente; "Renata Vasconti" → diferente
  (tarja diz "Renata Duarte Vasconti"); "Carlos Taviao" → acento diferente (conferir).
- Ortografia: 4 avisos em 10 aulas (antes da calibragem: ~25, quase tudo lixo de OCR):
  "pápeis" → papéis (Moreno 04:51 — ERRO REAL, confirmado pelo JP em 15/10, passou na
  revisão anterior), "Contracolonizar" (Nego Bispo), "autodescritivo" (Design),
  "Autoatenção" (Atenção) — palavras válidas fora do dicionário: "Aceitar" uma vez.
- Tempo da etapa 2: 9 a 25 s por aula na máquina virtual do Mac (≈ 1 s por minuto de
  aula; a varredura da tarja é a maior parte), mais ~5 s uma vez por sessão para carregar
  os dicionários. Até 4 Tesseracts ao mesmo tempo. No app nativo do M1 deve cair (medir
  na etapa 6). Se precisar: parar a varredura alguns segundos depois de ler o nome
  cadastrado.
- Sintéticos: aula A com tarja genérica "Nome do Professor", "Previdênsia" e
  "previdenciaria"; aula B com tarja certa e "Habeas corpus e machine learning" (latim e
  inglês não podem virar aviso). Resultado: 41/41 (34 da etapa 1 + tarja genérica,
  2 erros de ortografia e os textos novos), 0 alarmes falsos.

Limites conhecidos da etapa 2:
- Palavra sem acento que também é palavra válida não é pega ("Salario" = verbo salariar;
  "media" = verbo mediar). É limite do dicionário.
- Erro de uma letra no fim que coincide com texto cortado em outra leitura pode passar
  ("Previdênci" quando "Previdência" aparece em outro lugar).
- Letra de mão (lousa/TV) não é checada (OCR não lê bem).
- App final: levar o Tesseract dentro do pacote (Mac: binário + dylibs; Windows: build
  UB-Mannheim) na pasta bin/; TESSDATA vem de revisor/data/tessdata.

## Situação
- Etapa 5 (Resumo final, SRT, pacote entre computadores, relatório do mês, configurações) — feita
  (19/10), testada no Chromium com as aulas sintéticas. Ver "Etapa 5".
- Etapa 4 (tela de revisão completa: itens, comentários, cópia, trecho de 8 s, zoom, G, P, atalhos,
  ignorar/aceitar, ajustes sem reanalisar) — feita (19/10), testada no Chromium com as aulas
  sintéticas. Ver "Etapa 4".
- Etapa 3 (telas Início, Análise, Resumo geral + servidor local) — feita (18/10), testada com
  as aulas sintéticas no navegador. Ver "Etapa 3".
- Etapa 2b (fala) — feita e calibrada (16/10): bruto real 7/7 erros avisados; 10 aulas
  aprovadas com 0 avisos de fala. Corte no meio da fala: os 6 eram alarme falso (JP ouviu,
  19/10) → virou só marca na forma de onda, não aviso.
  SPEECH_VERSION = 2. ANALYSIS_VERSION = 8 (não mudou).
- Etapa 2 (OCR + ortografia + tarja) — feita e calibrada com as 10 aulas (ver "Etapa 2").
  Sintéticos 41/41, 0 alarmes falsos.
- Etapa 1 (motor) — feita e calibrada com 10 aulas reais. Pendência: aula de TV.
- Etapa 6 (app empacotado Mac/Windows pelo GitHub Actions, com tudo dentro) — feita (19/10). Ver
  "Etapa 6". Falta o JP testar no Mac (casa e trabalho) e no Windows com as aulas reais.
- Pedidos do JP de 21/10 (fila de pastas, ↑ ↓ nos cortes, Próxima aula, abas, trecho com duração,
  medidor de áudio) — feitos (21/10). Ver "Pedidos do JP depois do uso no dia a dia".
- ANTIVÍRUS (22/10, 11h): o JP pôs no Windows e o antivírus acusou "trojan" (falso positivo; nome exato
  do alerta ainda não informado). Causas prováveis: app sem assinatura + PyInstaller + PowerShell escondido
  com -EncodedCommand e Add-Type/AttachThreadInput/SetForegroundWindow (janela de pasta, montagem 3/4).
  Decisão do JP: no Windows, SÓ o navegador de pastas do app (dialogs.py levanta Unsupported no Windows;
  /api/state "native_dialog": false → choose() vai direto ao browse()). Tirados: scripts PowerShell,
  packaging/check_dialog_ps.py e o passo "Janela de escolher pasta" do montar.yml. Nome da placa de vídeo
  lido do registro (winreg), não do PowerShell. montar.yml: passo "Sem PowerShell no app (Windows)" falha
  se o código chamar powershell/pwsh/EncodedCommand; bootloader do PyInstaller montado do código no Windows
  (PYINSTALLER_COMPILE_BOOTLOADER=1, --no-binary pyinstaller). Navegador do app: atalhos Área de Trabalho,
  Downloads, Vídeos, Filmes, Documentos; título conforme o pedido; dica de colar o caminho.
  Se ainda acusar: enviar o arquivo à Microsoft (falso positivo) e/ou assinatura digital (TI da PUC ou
  Azure Trusted Signing).
- MAC DO GITHUB (22/10): macos-14 cancelado 4 vezes seguidas ("capacity constraints" das máquinas Mac arm64;
  o job nem começa). Trocado para macos-15 (também M1/arm64; deployment target 11.0 e check_macos_min continuam
  valendo; o cache dos programas usa a mesma chave). Se o macos-15 também faltar, esperar e rodar de novo.
- ONDE PARAMOS (22/10/2026, fim): montagem de teste com Vulkan no Windows (ver "Pedidos do JP de 22/10",
  item 4). Esperando o JP testar no Windows (aparece "Falas: na placa de vídeo (NVIDIA …)"?) e no Mac.
- (antes, 22/10 tarde): "Montagem 4 (teste)" = correções do Windows da montagem 3 + "Analisar de
  novo" + vectorscope colorido (ver "Pedidos do JP de 22/10"); Mac e Windows TUDO OK no diagnóstico. Esperando
  o teste do JP; se aprovar, versão oficial 1.0.1 no mesmo commit. Trello (imagem + texto juntos) e Vulkan:
  explicados ao JP, esperando a decisão dele.
- (antes) versão oficial = 1.0.0 (Mac testado pelo JP: "perfeito"). A "Montagem 3
  (teste)" corrige os 2 problemas do Windows (análise travada em 93% e janela de pasta atrás do navegador;
  ver "Correções do Windows") e ESPERA o teste do JP no Windows. Se ele aprovar: Run workflow com
  sistemas=ambos e versao=1.0.1 no commit testado. Se a janela ainda abrir atrás: no Windows, ir direto
  para o navegador de pastas do app. O JP tem novas sugestões (conversa nova).
- Licenças (pergunta do JP, 21/10): tudo da LICENCAS-DE-TERCEIROS.md permite uso comercial; GPL obriga
  só a manter o código aberto (já está). Único ponto: patentes do H.264 (Via LA; 100 mil unidades/ano
  grátis, cobrança só para quem vende) — irrelevante para uso interno/gratuito.
- Pendentes antigos: juntar avisos de imagem
  congelada muito próximos (no Mac do GitHub saíram 2 a 7 frames de distância), "texto saiu" logo depois
  da vinheta de abertura (alarme falso), "ensinar formato" (aula de TV), END_TOLERANCE nas configurações,
  GPU no Windows para a fala se ficar lenta.
- Como trabalhar numa conversa nova: o repositório é github.com/jprodriguesgm/revisor-de-videos (PÚBLICO).
  Ler PROJETO.md; testar (pytest + tools/ui_smoke.py + tools/ui_novidades.py); montar SEMPRE "ambos".
  Versão de TESTE: aba Actions → Run workflow (ou API workflow_dispatch com sistemas=ambos) → Release
  "Montagem N (teste)", pré-lançamento. Versão OFICIAL (o JP aprovou o teste, no MESMO commit testado):
  Run workflow com o campo "Versão oficial" = X.Y.Z (API: inputs[versao]=1.1.0, sistemas=ambos) → Release
  "Revisor de Vídeos X.Y.Z" com a etiqueta vX.Y.Z, que o link /releases/latest entrega às equipes.
  (O proxy do ambiente do Claude não deixa enviar etiquetas por git push nem pela API; por isso o campo.)
  Atualizar o GUIA.md quando uma função mudar.
- Começar uma conversa nova a cada etapa (ler só este arquivo) para gastar menos.

## Código (pasta revisor/)
- server.py: servidor local + rotas /api/* (estado, pasta, começar, análise, revisão, editor,
  vectorscope em PNG, janelas do sistema, navegador de pastas; etapa 4: video, frame.jpg, fscope.png,
  media (Range), clip, comment, dismiss, accept, review/adjust, pick). __main__.py: sem argumentos abre o app.
- frames.py: JPEG do frame (miniatura/cheio) feito na hora e guardado no cache, frames YUV na memória,
  gráficos do frame em PNG, trecho de 8 s (MP4/WebM).
- ui/revisao.js: tela de revisão (etapa 4; ↑ ↓ cortes, Próxima aula, trecho com duração e medidor de
  áudio em 21/10). ui/app.js: as outras telas e utilidades (fila de pastas em 21/10).
- tools/ui_novidades.py: teste no navegador dos pedidos de 21/10.
- export.py (etapa 5): texto copiado, SRT, horas por editor e txt, pacote (exportar, ler, juntar),
  relatório do mês (txt e CSV). ui/final.js: Resumo final, pacote, relatório do mês e configurações.
- appdata.py: pasta do usuário e configurações. review.py: revisão salva. jobs.py: análise em
  segundo plano. summary.py: números e avisos para as telas. dialogs.py: janelas do sistema.
- ui/: index.html, app.css, app.js (telas), fonts/ (IBM Plex, OFL).
- timecode.py: formatos de tempo (testes em tests/test_timecode.py).
- media.py: FFmpeg (probe, leitura exata de frames, JPEG, áudio + EBU R128, canal alfa).
- audio.py: janelas de 10 ms; mín/máx/média, LUFS; avisos clip, spike, gap, level_jump,
  noise_change, long_silence. Ignora as vinhetas nos números. Calibrado para áudio com gate.
- video.py: passada leve 4 fps 320×180 (blocos 10×10: brilho+bordas; cor 9×16);
  cortes; mudanças locais que ficam (≈2 s parado antes/depois) fora da zona de movimento
  do professor (por plano); cor/brilho que mudam de repente; imagem congelada; refino ao
  frame exato; agrupamento de listas; entrada×saída de texto; sensibilidade = limiar
  sobre a nota (sem reanalisar).
- transitions.py: trajetória do slide em cada corte, moldura (bordas) e regra da aula.
- vinheta.py: alinhamento frame a frame com os arquivos de vinheta (com transparência);
  5 frames de cada transição; avisos de vinheta cortada/ausente.
- scopes.py: conta-gotas, waveform/parade/vectorscope do frame, alvos Rec.709.
- ocr.py: Tesseract (leituras, releitura ampliada, varredura da tarja com recortes empilhados).
- spell.py: dicionários (spylls), regras do que checar, sugestões, lista própria.
- nametag.py: regra da tarja (ok / acento / diferente / genérico / não achada / lido).
- tools/text_only.py: roda só a etapa 2 em análises do cache (calibragem).
- speech.py: transcrição (whisper-cli em pedaços), frases de erro, takes repetidos.
- audio.py também: corte no meio da fala nos cortes do vídeo (predição linear).
- report.py: leitura do txt de tempo e casamento txt × vídeos da pasta. analyze.py: orquestra e grava o cache
  (ANALYSIS_VERSION muda quando a análise muda: o cache antigo é refeito).
- tools/make_test_videos.py e tools/evaluate.py: vídeos com gabarito e medição.

Limites conhecidos: texto que entra por cima da área onde o professor se mexe pode
passar; travadinhas curtas (2–10 frames repetidos) ainda não são procuradas.
