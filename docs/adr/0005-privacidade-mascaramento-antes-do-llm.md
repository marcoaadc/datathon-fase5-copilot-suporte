# ADR 0005 — Privacidade: mascaramento antes do LLM e nenhum conteúdo em logs

**Status:** aceito

## Contexto

Clientes escrevem dados pessoais em chamados sem que ninguém peça: CPF, telefone, e-mail, a senha do Wi-Fi. A pergunta do `/chat` é enviada a um provedor de LLM externo, o que configura compartilhamento com um operador e, em geral, transferência internacional de dados (LGPD, arts. 33 a 36).

## Decisão

1. **Minimização na fronteira:** todo texto que sai da aplicação rumo ao LLM passa antes pelo mascaramento (`guardrails/pii.py`). O dado é trocado por um marcador (`[CPF]`, `[CNPJ]`, `[RG]`, `[EMAIL]`, `[TELEFONE]`, `[CARTAO]`, `[CEP]`, `[NASCIMENTO]`, `[MAC]`, `[IP]`, `[SENHA]`, `[NOME]`), que preserva o sentido da frase.
2. **Validação reduz falso positivo:** CPF e CNPJ só são mascarados se os dígitos verificadores conferem; cartão, se passa no algoritmo de Luhn; IP, só se for público (192.168.x.x faz parte do suporte e precisa chegar ao LLM).
3. **Tudo local até o mascaramento:** triagem, embeddings e busca rodam dentro da aplicação. O LLM é o único destino externo, e recebe o texto já mascarado.
4. **Sem persistência de conteúdo:** a API não grava chamados, perguntas nem respostas. Logs e métricas carregam identificadores, contagens, durações e códigos de regra. Erros de validação não ecoam o valor recebido.
5. **Monitor de drift sem texto:** guarda dez números por chamado, em memória.
6. **Saída também é verificada:** dado pessoal na resposta que não venha do manual é mascarado.

## Alternativas consideradas

- **NER (modelo de reconhecimento de entidades):** detectaria nomes e endereços em texto livre, que os padrões não cobrem. Adiciona um modelo e latência; fica como evolução, e a limitação está declarada no README.
- **Pseudonimização reversível (tokenização com cofre):** permitiria ao LLM tratar "o cliente A" de forma consistente e restaurar o dado na resposta. Não há caso de uso aqui: a resposta vem do manual e não precisa do dado do cliente.
- **Não enviar nada ao LLM (só modo extrativo):** é o que a aplicação faz sem chave configurada, e continua disponível por configuração (`COPILOT_LLM_PROVIDER=offline`) para operações que não possam contratar um operador externo.

## Consequências

- Nomes só são detectados em construções explícitas ("meu nome é...", "my name is...") e com inicial maiúscula; endereços residenciais não são detectados. Esse é o risco residual principal.
- O mascaramento precisa errar pouco para os dois lados. A primeira versão do padrão de senha tratava a conjunção "e" como "é" e mascarava palavras comuns em "esqueci a senha do roteador e preciso redefinir": a pergunta mais frequente do suporte chegava mutilada à busca. Hoje o valor só é mascarado depois de `:`/`=`, entre aspas, ou quando tem dígito ou símbolo.
- O mascaramento é irreversível por desenho: a aplicação não tem como recuperar o dado depois.
- A contagem por tipo de dado mascarado é exposta na resposta (`pii_redacted`) e nas métricas, o que permite auditar o controle sem ver o dado.
