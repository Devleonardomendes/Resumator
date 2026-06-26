# Resumator 11.0

Aplicativo Windows para montar prompts de analise documental, enviar ate 10 PDFs para assistentes de IA, capturar a resposta e exportar em PDF, DOCX, JSON ou diretamente para o QUIMERA.

## Download

Baixe o instalador Windows em [`downloads/Resumator_11.0_Setup.exe`](downloads/Resumator_11.0_Setup.exe).

Versao 11.0: inclui suporte ao DeepSeek, preserva a formatacao capturada da IA nas exportacoes DOCX/PDF e mantem JSON/QUIMERA em texto puro.

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

1. Abra o Resumator 11.0.
2. Crie um prompt em "Personalizado", importe prompts ou use o "Assistente".
3. Selecione de 1 a 10 PDFs.
4. Escolha o destino de IA.
5. Escolha o modo de envio: texto colado ou documento DOCX.
6. Envie o prompt e os documentos.
7. Capture a resposta da IA ou cole o texto manualmente.
8. Exporte em PDF, DOCX, JSON, acione o QUIMERA ou importe um DOCX para gerar PDF.

## Automacao local

A automacao atua somente nos destinos cadastrados: ChatGPT Desktop, Microsoft 365 Copilot, Google Gemini, LM Studio Desktop e DeepSeek. Ela usa apenas os PDFs selecionados no Resumator e registra logs de tentativa.

No modo "Texto colado", o prompt e colado no campo de mensagem e os PDFs sao anexados conforme a opcao selecionada.

No modo "Documento DOCX", o Resumator cria um DOCX temporario com o prompt e anexa esse arquivo junto dos PDFs.

No Microsoft 365 Copilot, o Resumator 11.0 sempre abre um novo chat por solicitacao, cola o prompt como texto e anexa apenas os PDFs selecionados. Se o seletor de arquivos nao for confirmado, o envio fica pausado para conferencia.

Copilot, Gemini e DeepSeek podem mudar a interface. Quando o botao de anexo nao for encontrado pelo Windows UI Automation, o Resumator tenta alternativas de anexo e mantem o envio pausado para conferencia quando necessario.

A captura automatica procura o botao "Copiar" da resposta mais recente. Quando o clipboard da IA fornece HTML, o Resumator preserva essa formatacao para exportar DOCX e PDF. A integracao com QUIMERA e a exportacao JSON continuam usando texto sem formatacao.

## Integracao com QUIMERA

O botao direto usa o argumento --summary-file do QUIMERA. Use o QUIMERA atualizado junto com o Resumator 11.0. A exportacao manual em JSON continua disponivel como alternativa.

## Arquivos principais

- `app.py`: entrada do aplicativo.
- `resumator/`: codigo fonte principal do projeto local.
- `data/prompts.json`: arquivo inicial de prompts da versao.
- `README.txt`: documentacao em texto aberta pelo botao Readme.
- `saidas/`: pasta padrao para PDF, DOCX e logs quando usado em modo fonte.

## Build

Aplicativo:

```powershell
python -m PyInstaller --noconfirm --clean --distpath dist-py314 --workpath build-py314 "Resumator 11.0.spec"
```

Instalador:

```powershell
powershell -ExecutionPolicy Bypass -File installeruild_setup.ps1
```

Artefatos esperados:

- `dist-py314\Resumator 11.0\Resumator 11.0.exe`
- `dist-py314\Resumator 11.0 Setup.exe`
