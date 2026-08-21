# Conformidade GitHub — repositórios bloqueados ou indisponíveis

A tela **Conformidade** do ARGWS Git Monitor permite tentar remover da própria conta GitHub um repositório ou fork que deixou de aparecer no catálogo normal por bloqueio, indisponibilidade ou restrição legal/DMCA.

## O que a ferramenta faz

1. usa uma conexão GitHub já cadastrada no Git Monitor;
2. recebe o nome completo no formato `owner/repo`;
3. valida que `owner` é a própria conta da conexão selecionada;
4. consulta a API oficial do GitHub sem tentar ler ou recuperar o conteúdo bloqueado;
5. classifica a resposta como acessível, restrição legal (HTTP 451), acesso negado (403), não visível (404) ou token não autorizado (401);
6. gera uma confirmação forte no formato `EXCLUIR owner/repo`;
7. chama exclusivamente `DELETE /repos/{owner}/{repo}`;
8. se o GitHub confirmar a exclusão, remove também o registro local do monitor e grava a ação na trilha de auditoria.

## O que a ferramenta não faz

- não contorna DMCA ou outra restrição legal;
- não restaura um repositório bloqueado;
- não baixa ou copia o conteúdo indisponível;
- não remove repositórios de outra conta ou organização por essa tela;
- não tenta burlar uma resposta 451/403 do GitHub.

Se o próprio endpoint de exclusão for recusado por restrição legal, o Git Monitor encerra a operação e informa que a remoção precisa ser tratada pelo suporte do GitHub.

## Permissões do token

A exclusão depende das permissões aceitas pelo GitHub para o tipo de token utilizado. Em geral, o token precisa de permissão administrativa de escrita sobre o repositório; tokens clássicos podem exigir o escopo específico de exclusão de repositórios.

## Segurança

A operação exige duas confirmações:

- o `owner/repo` deve pertencer à conta GitHub conectada;
- o usuário precisa digitar exatamente `EXCLUIR owner/repo`.

A exclusão é permanente do ponto de vista da aplicação e deve ser usada somente quando o objetivo for retirar a cópia/fork da própria conta.
