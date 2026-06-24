Resumator 10.1
==============

Aplicativo Windows para montar prompts de analise documental, enviar ate 10 PDFs para assistentes de IA, capturar a resposta e exportar em PDF, DOCX, JSON ou diretamente para o QUIMERA.

Download
--------

Baixe o instalador Windows em downloads\Resumator_10.1_Setup.exe.

Tutorial de excecao no Windows: TUTORIAL_EXCECAO_FIREWALL_WINDOWS.txt.

Versao atualizada em 24/06/2026 com bloqueio de novos PDFs apos a escolha da IA, nome de exportacao baseado no numero do processo e instalador da versao 10.1.

Assistente de Prompt
--------------------

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

Uso basico
----------

1. Abra o Resumator 10.1.
2. Crie um prompt em "Personalizado", importe prompts ou use o "Assistente".
3. Selecione de 1 a 10 PDFs.
4. Escolha o destino de IA.
5. Escolha o modo de envio: texto colado ou documento DOCX.
6. Envie o prompt e os documentos.
7. Capture a resposta ou cole o texto manualmente.
8. Exporte em PDF, DOCX, JSON ou acione o QUIMERA.

Automacao local
---------------

A automacao atua somente nos destinos cadastrados: ChatGPT Desktop, Microsoft 365 Copilot, Claude Desktop, Google Gemini, LM Studio Desktop e Jus IA. Ela usa apenas os PDFs selecionados no Resumator e registra logs de tentativa.

No modo "Texto colado", o prompt e colado no campo de mensagem e os PDFs sao anexados conforme a opcao selecionada.

No modo "Documento DOCX", o Resumator cria um DOCX temporario com o prompt e anexa esse arquivo junto dos PDFs.

No Microsoft 365 Copilot, o Resumator 10.1 sempre abre um novo chat por solicitacao, cola o prompt como texto e anexa apenas os PDFs selecionados. Se o seletor de arquivos nao for confirmado, o envio fica pausado para conferencia.

Copilot, Gemini e Claude podem mudar a interface. Quando o botao de anexo nao for encontrado pelo Windows UI Automation, o Resumator tenta colar os arquivos como anexos e mantem o envio pausado para conferencia.

Integracao com QUIMERA
----------------------

O botao direto usa o argumento --summary-file do QUIMERA. Use o QUIMERA atualizado junto com o Resumator 10.1. A exportacao manual em JSON continua disponivel como alternativa.

Arquivos principais
-------------------

- app.py: entrada do aplicativo.
- resumator\: codigo fonte principal do projeto local.
- data\prompts.json: arquivo inicial de prompts da versao, distribuido vazio.
- README.txt: documentacao em texto aberta pelo botao Readme.
- saidas\: pasta padrao para PDF, DOCX e logs quando usado em modo fonte.

Build
-----

Aplicativo:

python -m PyInstaller --noconfirm --clean --distpath dist-py314 --workpath build-py314 "Resumator 10.1.spec"

Instalador:

powershell -ExecutionPolicy Bypass -File installer\build_setup.ps1

Artefatos esperados:

- dist-py314\Resumator 10.1\Resumator 10.1.exe
- dist-py314\Resumator 10.1 Setup.exe
