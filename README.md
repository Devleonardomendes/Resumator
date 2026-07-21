# Resumator 11.4

Aplicativo Windows para montar prompts de analise documental, enviar ate 10 PDFs para assistentes de IA, capturar a resposta e exportar em PDF, DOCX, JSON ou diretamente para o QUIMERA.

## Download

Baixe o instalador Windows em [`downloads/Resumator_11.4_Setup.exe`](downloads/Resumator_11.4_Setup.exe).

Versao 11.4: mantem todos os recursos e correcoes da versao 11.3 e substitui a confirmacao exibida apos a exportacao em DOCX ou PDF por uma animacao de 3 segundos com a risada do personagem.

Versao 11.3: mantem o comportamento da versao anterior e corrige a colagem de texto no Microsoft 365 Copilot e no Google Gemini. Antes de colar ou enviar, o Resumator localiza e confirma o foco no campo de mensagem; se isso nao for possivel, interrompe a automacao para evitar colagem no local errado.

Revisao de estabilidade da versao 11.3: o atalho instalado do Gemini agora e localizado recursivamente nas pastas de aplicativos do Windows, independentemente do idioma da pasta ou do nome `Gemini`/`Google Gemini`. O Resumator abre maximizado pelo modo nativo do Windows, sem tela cheia e sem cobrir a barra de tarefas. ChatGPT Work, Microsoft 365 Copilot, Google Gemini, LM Studio Desktop e DeepSeek sao apenas trazidos para frente: tamanho, estado e controles de redimensionamento de suas janelas nao sao alterados. Para Copilot e Gemini, "Enviar ao final" permanece bloqueado; com mais de um PDF, a anexacao automatica inicia desmarcada e pode ser habilitada manualmente.

## Assistente de Prompt

O botao "Assistente" abre uma janela grande com alternativas de escolha unica para:

1. Perfil do usuario:
- advogado de pessoa fisica ou empresa privada
- procurador da Uniao ou de Autarquia Federal
- especialista de Agencia Reguladora
- analista processual do Poder Judiciario

2. Conhecimento especializado da IA:
- membro de corregedoria de orgao publico
- Direito Civil e Empresarial
- Direito administrativo com enfoque em processo administrativo disciplinar
- Direito Publico (Direito Tributario e Direito administrativo em geral)
- Direito Processual Civil
- Direito Minerario e engenharia de mineracao
- Direito e Engenharia do Petroleo, Gas Natural e Biocombustiveis
- Direito no campo da Saude Suplementar
- Transportes terrestres (ANTT) e Direito de transito
- Metrologia, Qualidade e Tecnologia
- Direito Ambiental e Engenharia Ambiental
- Vigilancia Sanitaria
- Direito Previdenciario
- Titulos e Valores Mobiliarios
- Direito Maritimo

3. Documento analisado:
- documento unico
- processo administrativo
- processo judicial do Eproc
- processo judicial do PJe
- dossie de processo judicial baixado do SuperSapiens

4. Resultado esperado:
- Relatorio objetivo imparcial
- Relatorio detalhado imparcial
- Relatorio e analise administrativa e juridica objetiva
- Relatorio e analise administrativa e juridica detalhada

5. Opiniao:
- a IA devera sugerir a medida a ser adotada
- a IA nao devera opinar

## Uso basico

1. Abra o Resumator 11.4.
2. Informe o número do processo administrativo/judicial.
3. Crie ou selecione um prompt em "Personalizado", importe prompts ou use o "Assistente".
4. Selecione de 1 a 10 PDFs ou arraste os PDFs para "Adicionar PDF".
5. Escolha o destino de IA.
6. Confira o modo de envio. "Texto colado" e "Somente texto colado" ficam marcados por padrao. No Copilot e no Gemini, "Enviar ao final" fica desmarcado e bloqueado. Com mais de um PDF nesses dois destinos, "Anexar PDFs automaticamente" inicia desmarcado, mas pode ser habilitado manualmente.
7. Envie o prompt e os documentos.
8. Capture a resposta da IA ou cole o texto manualmente.
9. Exporte em PDF, DOCX, JSON, acione o QUIMERA ou importe um DOCX para gerar PDF.

## Automacao local

A automacao atua somente nos destinos cadastrados: ChatGPT Work, Microsoft 365 Copilot, Google Gemini, LM Studio Desktop e DeepSeek. Ela usa apenas os PDFs selecionados no Resumator e registra logs de tentativa.

A janela principal abre maximizada pelo modo nativo do Windows, sem usar tela cheia e respeitando a area da barra de tarefas. O Assistente de Prompt e o Editor de Prompt permanecem maximizados e sem redimensionamento. As janelas de todas as IAs somente recebem foco, sem qualquer tentativa de maximizar, restaurar, bloquear o redimensionamento ou alterar seus estilos. O seletor de arquivos permanece com tamanho normal para permitir a escolha dos anexos.

No novo aplicativo ChatGPT para Windows, o Resumator abre o pacote oficial pelo identificador estavel do aplicativo e sempre seleciona e confirma o modo ChatGPT Work. Janelas auxiliares, como Dictation, Debug ou Codex, sao ignoradas. Se o modo Work ou o foco da janela principal nao puder ser confirmado, a automacao para antes de colar ou enviar qualquer conteudo.

No modo "Texto colado", o prompt e colado no campo de mensagem antes da anexacao dos PDFs. Depois de colar o prompt, o Resumator aguarda 2 segundos antes de anexar o primeiro PDF.

Quando ha mais de um PDF, o Resumator aguarda 3 segundos apos cada anexo antes de iniciar o proximo.

No modo "Documento DOCX", o Resumator cola o prompt como texto, cria um DOCX temporario com o prompt e anexa esse DOCX antes dos PDFs.

No Microsoft 365 Copilot, o Resumator 11.4 sempre abre um novo chat por solicitacao, confirma o foco no campo de mensagem, cola o prompt como texto e anexa apenas os PDFs selecionados. No Google Gemini, o campo de mensagem tambem e localizado e focado antes da colagem. Se o campo ou o seletor de arquivos nao for confirmado, o envio fica pausado para conferencia.

Ao abrir o Gemini, o Resumator procura primeiro os atalhos `Gemini.lnk` e `Google Gemini.lnk` nas pastas de programas e areas de trabalho do usuario e do sistema, incluindo subpastas localizadas como `apps do Chrome`. A URL do Gemini e usada somente quando nenhum atalho instalado e encontrado.

Copilot, Gemini e DeepSeek podem mudar a interface. Quando o botao de anexo nao for encontrado pelo Windows UI Automation, o Resumator tenta alternativas de anexo e mantem o envio pausado para conferencia quando necessario.

A captura automatica bloqueia o mouse por 5 segundos e procura o botao "Copiar" da resposta mais recente. No Gemini, a busca tenta revelar os botoes da ultima resposta e repete algumas vezes, pois a interface pode ocultar o botao enquanto a resposta ainda esta em geracao. Quando o clipboard da IA fornece HTML, o Resumator preserva essa formatacao para exportar DOCX e PDF, ignorando blocos tecnicos como CSS do Copilot. A integracao com QUIMERA e a exportacao JSON continuam usando texto sem formatacao.

PDF e DOCX exportados usam o formato `Resumator_(numero do processo)_(IA)`, por exemplo `Resumator_0154064-23.2015.4.02.5117_Copilot.docx`.

## Integracao com QUIMERA

O botao direto usa o argumento --summary-file e prefere o QUIMERA 4.2, mantendo o QUIMERA 4.1 como fallback. A exportacao manual em JSON continua disponivel como alternativa.

## Arquivos principais

- `app.py`: entrada do aplicativo.
- `resumator/`: codigo fonte principal do projeto local.
- `data/prompts.json`: arquivo inicial de prompts da versao.
- `README.txt`: documentacao em texto aberta pelo botao Readme.
- `saidas/`: pasta padrao para PDF, DOCX e logs quando usado em modo fonte.

## Build

Aplicativo:

```powershell
python -m PyInstaller --noconfirm --clean --distpath dist-py314 --workpath build-py314 "Resumator 11.4.spec"
```

Instalador:

```powershell
powershell -ExecutionPolicy Bypass -File installer\build_setup.ps1
```

Artefatos esperados:

- `dist-py314\Resumator 11.4\Resumator 11.4.exe`
- `dist-py314\Resumator 11.4 Setup.exe`
