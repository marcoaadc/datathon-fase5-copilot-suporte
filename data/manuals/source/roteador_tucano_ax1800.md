# Manual do Usuário - Roteador Wi-Fi 6 Tucano AX1800

Modelo TC-AX1800 | Versão do documento 2.3 | Firmware de referência 1.4.2

Este manual descreve a instalação, a configuração e a solução de problemas do roteador Tucano AX1800. Leia as instruções de segurança antes de ligar o equipamento. O produto, o fabricante e os contatos citados neste documento são fictícios e foram criados para fins educacionais.

## 1 Visão geral do produto

O Tucano AX1800 é um roteador doméstico de banda dupla compatível com o padrão Wi-Fi 6 (IEEE 802.11ax). Ele distribui a conexão de internet recebida do modem da operadora para dispositivos com fio e sem fio, e pode trabalhar em conjunto com outras unidades Tucano para formar uma rede mesh.

### 1.1 Conteúdo da embalagem

- 1 roteador Tucano AX1800
- 1 fonte de alimentação bivolt de 12 V e 1,5 A
- 1 cabo de rede Ethernet categoria 5e com 1,5 metro
- 1 guia rápido de instalação
- 1 etiqueta com o nome da rede e a senha de fábrica, colada na base do roteador

### 1.2 Especificações técnicas

- Padrões sem fio: IEEE 802.11ax, 802.11ac, 802.11n, 802.11g e 802.11b
- Velocidade nominal: até 574 Mbps na faixa de 2,4 GHz e até 1201 Mbps na faixa de 5 GHz
- Portas: 1 porta WAN Gigabit (azul) e 4 portas LAN Gigabit (amarelas)
- Antenas: 4 antenas externas fixas de 5 dBi
- Processador de dois núcleos de 1,2 GHz, 256 MB de memória RAM e 128 MB de armazenamento
- Segurança sem fio: WPA2-PSK, WPA3-SAE e modo misto WPA2/WPA3
- Capacidade recomendada: até 64 dispositivos conectados ao mesmo tempo
- Alimentação: 100 a 240 V na entrada da fonte, 12 V e 1,5 A na saída
- Temperatura de operação: de 0 a 40 graus Celsius
- Dimensões: 230 x 144 x 37 mm, com peso de 410 g

### 1.3 Painel frontal e LEDs

O painel frontal possui quatro LEDs. A leitura correta deles é a primeira etapa de qualquer diagnóstico.

- LED Power: verde fixo indica equipamento ligado. Verde piscando indica inicialização, que leva cerca de 90 segundos. Apagado indica falta de energia.
- LED Internet: verde fixo indica conexão com a internet estabelecida. Laranja fixo indica cabo conectado na porta WAN, mas sem acesso à internet. Vermelho piscando indica falha de autenticação PPPoE. Apagado indica que não há cabo na porta WAN.
- LED Wi-Fi: verde fixo indica rede sem fio ativa. Verde piscando rápido indica tráfego de dados. Azul piscando indica que o WPS está aguardando um dispositivo. Apagado indica Wi-Fi desativado.
- LED Mesh: branco fixo indica sinal bom entre as unidades. Amarelo fixo indica sinal fraco. Vermelho fixo indica que a unidade perdeu a conexão com o roteador principal.

### 1.4 Painel traseiro

Da esquerda para a direita, o painel traseiro traz: o conector de energia, o botão liga/desliga, a porta WAN azul, as quatro portas LAN amarelas, o botão WPS e o botão RESET, que fica embutido e precisa de um clipe ou objeto fino para ser pressionado.

## 2 Instalação

### 2.1 Onde posicionar o roteador

O local de instalação influencia diretamente o alcance e a velocidade do Wi-Fi. Siga estas recomendações:

- Instale o roteador em um ponto central da residência, a pelo menos 1,5 metro do chão.
- Mantenha distância mínima de 1 metro de micro-ondas, telefones sem fio, babás eletrônicas e aquários.
- Evite armários fechados, nichos de metal e a parte de trás de televisores.
- Deixe as antenas na posição vertical. Em casas de dois andares, incline duas antenas a 45 graus.
- Não instale o equipamento em locais expostos ao sol, à umidade ou sem ventilação.

### 2.2 Conexão dos cabos

1. Desligue o modem da operadora e aguarde 30 segundos.
2. Conecte o cabo de rede entre a porta LAN do modem e a porta WAN azul do roteador.
3. Ligue o modem e aguarde 2 minutos até que os LEDs dele estabilizem.
4. Conecte a fonte de alimentação ao roteador e pressione o botão liga/desliga.
5. Aguarde cerca de 90 segundos, até o LED Power ficar verde fixo.

### 2.3 Primeiro acesso ao painel de administração

1. Conecte um computador ou celular à rede Wi-Fi indicada na etiqueta da base do roteador. O nome de fábrica segue o formato Tucano_XXXX, em que XXXX são os quatro últimos caracteres do número de série.
2. Abra o navegador e acesse o endereço http://192.168.10.1 ou http://tucano.local.
3. Informe o usuário admin e a senha de administração impressa na etiqueta.
4. No primeiro acesso, o assistente de configuração exige a criação de uma nova senha de administração com pelo menos 10 caracteres, contendo letras e números.
5. Escolha o tipo de conexão com a internet, defina o nome e a senha da rede Wi-Fi e conclua o assistente.

Após 5 tentativas de login incorretas, o painel fica bloqueado por 15 minutos. O painel de administração encerra a sessão automaticamente após 10 minutos sem uso.

### 2.4 Aplicativo Tucano Casa

O aplicativo Tucano Casa, disponível para Android 9 ou superior e iOS 15 ou superior, permite configurar o roteador, ver os dispositivos conectados, pausar a internet de um dispositivo e receber avisos de atualização. O aplicativo só gerencia o roteador a partir da própria rede local, a menos que o acesso remoto seja ativado conforme a seção 5.5.

## 3 Configuração da rede Wi-Fi

### 3.1 Alterar o nome e a senha do Wi-Fi

1. Acesse o painel de administração em http://192.168.10.1.
2. Abra o menu Wi-Fi e depois a opção Rede principal.
3. Altere o campo Nome da rede (SSID). O nome pode ter até 32 caracteres.
4. Altere o campo Senha. A senha deve ter entre 8 e 63 caracteres.
5. Clique em Salvar. O roteador reinicia o Wi-Fi em cerca de 20 segundos e todos os dispositivos precisam se conectar novamente com a nova senha.

Recomendação: use uma senha com pelo menos 12 caracteres e evite dados pessoais como nome, data de nascimento ou telefone.

### 3.2 Faixas de 2,4 GHz e 5 GHz

O roteador transmite em duas faixas de frequência. A faixa de 2,4 GHz tem maior alcance e atravessa melhor as paredes, mas é mais lenta e sofre mais interferência. A faixa de 5 GHz é mais rápida, porém tem alcance menor.

Por padrão, a função Conexão Inteligente fica ativada: as duas faixas usam o mesmo nome de rede e o roteador escolhe automaticamente a melhor faixa para cada dispositivo. Alguns dispositivos antigos de automação residencial, como tomadas e lâmpadas inteligentes, só funcionam em 2,4 GHz e podem falhar ao parear com a Conexão Inteligente ativada. Nesse caso, desative a função no menu Wi-Fi, opção Avançado, e a rede de 5 GHz passará a aparecer com o sufixo _5G.

### 3.3 Rede de convidados

A rede de convidados dá acesso à internet sem permitir acesso aos dispositivos da rede principal, como impressoras, câmeras e computadores.

1. No menu Wi-Fi, abra a opção Convidados.
2. Ative a rede e defina um nome e uma senha próprios.
3. Opcionalmente, defina um tempo de expiração de 4 horas, 1 dia ou 7 dias.
4. Opcionalmente, limite a velocidade da rede de convidados. O limite padrão é de 20 Mbps.

A rede de convidados aceita no máximo 16 dispositivos simultâneos.

### 3.4 Conexão por WPS

O WPS permite conectar um dispositivo sem digitar a senha. Pressione o botão WPS no painel traseiro por 2 segundos: o LED Wi-Fi pisca em azul e o roteador aguarda o dispositivo por 2 minutos. O método de PIN do WPS é desativado de fábrica por segurança e não pode ser reativado. Quando a rede usa apenas WPA3, o WPS fica indisponível.

### 3.5 Canal e largura de banda

De fábrica, o roteador escolhe o canal automaticamente a cada reinicialização. Se houver muitas redes vizinhas, fixe o canal manualmente no menu Wi-Fi, opção Avançado:

- Em 2,4 GHz, use os canais 1, 6 ou 11, que não se sobrepõem, com largura de 20 MHz.
- Em 5 GHz, use os canais 36, 40, 44 ou 48 com largura de 80 MHz.

## 4 Rede e conexão com a internet

### 4.1 Tipos de conexão WAN

O tipo de conexão é definido no menu Internet. Consulte a sua operadora se tiver dúvida sobre qual usar.

- IP dinâmico (DHCP): é o padrão e o mais comum. O modem da operadora entrega o endereço automaticamente.
- PPPoE: exige usuário e senha fornecidos pela operadora. É usado quando o modem está em modo bridge.
- IP estático: exige endereço IP, máscara, gateway e DNS informados pela operadora. É comum em planos empresariais.

### 4.2 Rede local e servidor DHCP

O endereço padrão do roteador na rede local é 192.168.10.1, com máscara 255.255.255.0. O servidor DHCP distribui endereços de 192.168.10.100 a 192.168.10.199 e o tempo de concessão padrão é de 24 horas. Se o modem da operadora também usar a faixa 192.168.10.x, ocorre conflito de endereços: nesse caso, altere o endereço do roteador para 192.168.20.1 no menu Rede, opção LAN.

### 4.3 Reserva de endereço IP

A reserva garante que um dispositivo receba sempre o mesmo endereço, o que é necessário para impressoras, câmeras e redirecionamento de portas.

1. Abra o menu Rede e a opção Dispositivos conectados.
2. Localize o dispositivo e clique em Reservar IP.
3. Escolha um endereço dentro da faixa do DHCP e salve.

O roteador aceita até 32 reservas de endereço.

### 4.4 Redirecionamento de portas

O redirecionamento de portas permite que um serviço da rede local seja acessado pela internet, como um servidor de jogos ou um gravador de câmeras.

1. Reserve um endereço IP para o dispositivo de destino, conforme a seção 4.3.
2. Abra o menu Avançado e a opção Redirecionamento de portas.
3. Clique em Adicionar regra e informe o nome, a porta externa, a porta interna, o protocolo (TCP, UDP ou ambos) e o IP do dispositivo.
4. Salve. A regra entra em vigor imediatamente, sem reiniciar o roteador.

O roteador aceita até 24 regras de redirecionamento. As portas 80, 443 e 8443 do próprio roteador não podem ser redirecionadas enquanto o acesso remoto estiver ativado. Se a operadora usar CGNAT, o redirecionamento não funciona: solicite à operadora um endereço IP público.

### 4.5 Servidores DNS

Por padrão, o roteador usa os servidores DNS entregues pela operadora. Para usar outros servidores, abra o menu Internet, opção DNS, selecione Manual e informe o DNS primário e o secundário. A alteração vale para todos os dispositivos após a renovação da conexão ou a reinicialização do roteador.

### 4.6 Modo ponto de acesso

Use o modo ponto de acesso quando o modem da operadora já faz o roteamento e não pode ser colocado em modo bridge. Nesse modo, o Tucano AX1800 apenas distribui o Wi-Fi e deixa de aplicar firewall, controle parental e redirecionamento de portas. Ative em Avançado, opção Modo de operação. Depois da mudança, o painel de administração deixa de responder em 192.168.10.1 e passa a ser acessado por http://tucano.local.

### 4.7 IPv6

O suporte a IPv6 vem desativado de fábrica. Para ativar, abra o menu Internet, opção IPv6, e selecione o modo Automático. A ativação exige que a operadora ofereça IPv6 no plano contratado.

## 5 Segurança

### 5.1 Senha de administração

A senha de administração protege o painel de configuração e é diferente da senha do Wi-Fi. Para alterá-la, abra o menu Sistema, opção Administração. A senha deve ter pelo menos 10 caracteres, com letras e números. Nunca informe a senha de administração a terceiros: a equipe de suporte da Tucano nunca solicita essa senha por telefone, e-mail ou mensagem.

### 5.2 Criptografia da rede sem fio

O padrão de fábrica é o modo misto WPA2/WPA3, compatível com dispositivos novos e antigos. Use o modo WPA3 puro somente se todos os dispositivos da casa forem compatíveis. Os protocolos WEP e WPA com TKIP não são oferecidos por serem inseguros.

### 5.3 Firewall

O firewall vem ativado de fábrica e bloqueia conexões iniciadas pela internet que não correspondam a uma regra de redirecionamento. A proteção contra ataques de negação de serviço limita a 200 novas conexões por segundo vindas de um mesmo endereço. Não desative o firewall, exceto por orientação do suporte durante um diagnóstico.

### 5.4 Controle parental

O controle parental permite criar perfis e associar dispositivos a eles.

1. Abra o menu Controle parental e clique em Novo perfil.
2. Dê um nome ao perfil e selecione os dispositivos.
3. Defina os horários de bloqueio da internet. Cada perfil aceita até 4 faixas de horário por dia.
4. Opcionalmente, ative o filtro de conteúdo por categoria: adulto, jogos de azar, redes sociais e violência.

O roteador aceita até 8 perfis. O filtro de conteúdo depende do DNS do roteador e deixa de funcionar se o dispositivo usar um DNS configurado manualmente ou uma VPN.

### 5.5 Acesso remoto

O acesso remoto ao painel pela internet vem desativado de fábrica. Para ativá-lo, abra o menu Sistema, opção Acesso remoto, e vincule o roteador a uma conta no aplicativo Tucano Casa com verificação em duas etapas. O acesso remoto usa a porta 8443 e conexão criptografada. Desative o recurso quando não for mais necessário.

### 5.6 Filtro de endereços MAC

O filtro de MAC permite listar os dispositivos autorizados ou bloqueados na rede sem fio. A lista aceita até 64 endereços. O filtro não substitui uma senha forte, pois endereços MAC podem ser falsificados.

## 6 Manutenção

### 6.1 Atualização de firmware

As atualizações corrigem falhas de segurança e melhoram a estabilidade. A atualização automática vem ativada e ocorre entre 3h e 5h da manhã, quando há nova versão disponível.

Para atualizar manualmente:

1. Abra o menu Sistema, opção Atualização.
2. Clique em Verificar atualização.
3. Se houver nova versão, clique em Instalar.
4. Aguarde cerca de 5 minutos. O roteador reinicia sozinho ao final.

Atenção: nunca desligue o roteador da tomada durante a atualização. A interrupção pode danificar o equipamento. Se o LED Power ficar piscando em laranja por mais de 10 minutos depois de uma atualização, siga o procedimento de recuperação da seção 7.8.

### 6.2 Reinicialização

Reiniciar o roteador resolve a maior parte das instabilidades e não apaga nenhuma configuração. Use o botão liga/desliga, ou o menu Sistema, opção Reiniciar. A reinicialização leva cerca de 90 segundos. Também é possível agendar uma reinicialização semanal em Sistema, opção Agendamento.

### 6.3 Restauração de fábrica

A restauração de fábrica apaga todas as configurações: nome e senha do Wi-Fi, senha de administração, reservas de IP, regras de redirecionamento e perfis de controle parental.

1. Com o roteador ligado, pressione o botão RESET com um clipe por 10 segundos.
2. Solte o botão quando todos os LEDs piscarem ao mesmo tempo.
3. Aguarde cerca de 3 minutos até o LED Power ficar verde fixo.
4. Conecte-se à rede indicada na etiqueta da base e refaça a configuração inicial da seção 2.3.

Pressionar o botão RESET por menos de 3 segundos apenas reinicia o roteador, sem apagar as configurações.

### 6.4 Cópia de segurança das configurações

Antes de uma restauração de fábrica ou de uma troca de equipamento, salve as configurações em Sistema, opção Backup, clicando em Exportar. O arquivo gerado tem a extensão .tcfg e é protegido por uma senha definida no momento da exportação. Para restaurar, use a opção Importar. Um arquivo de backup só pode ser importado em um roteador do mesmo modelo com firmware igual ou mais recente.

## 7 Solução de problemas

### 7.1 Sem acesso à internet

Verifique primeiro a cor do LED Internet.

- LED Internet apagado: o cabo entre o modem e a porta WAN azul está desconectado ou com defeito. Reconecte o cabo ou troque-o por outro.
- LED Internet laranja fixo: o roteador está conectado ao modem, mas não recebe internet. Desligue o modem e o roteador da tomada, aguarde 30 segundos, ligue primeiro o modem, aguarde 2 minutos e só então ligue o roteador.
- LED Internet vermelho piscando: o usuário ou a senha PPPoE estão incorretos. Confira os dados no menu Internet ou solicite-os novamente à operadora.

Se o problema continuar, conecte um computador diretamente ao modem com um cabo. Se também não houver internet, a falha é da operadora e deve ser comunicada a ela.

### 7.2 Wi-Fi lento

1. Faça o teste de velocidade com um computador ligado por cabo a uma porta LAN. Se a velocidade por cabo também estiver baixa, o problema está no plano ou na operadora.
2. Aproxime o dispositivo do roteador e repita o teste. Se melhorar, o problema é de alcance: reposicione o roteador conforme a seção 2.1 ou adicione uma unidade mesh.
3. Verifique se o dispositivo está conectado na faixa de 5 GHz, que é mais rápida.
4. Troque o canal conforme a seção 3.5.
5. No menu Rede, opção Dispositivos conectados, verifique se algum dispositivo está consumindo a banda e, se necessário, limite a velocidade dele em Qualidade de serviço.

### 7.3 A conexão cai com frequência

- Verifique se o firmware está atualizado, conforme a seção 6.1.
- Confira se o roteador não está superaquecendo. A superfície não deve ultrapassar 40 graus Celsius; mantenha as aberturas de ventilação livres.
- Desative a Conexão Inteligente se as quedas ocorrerem apenas em um dispositivo antigo.
- Substitua o cabo entre o modem e o roteador.
- Agende uma reinicialização semanal, conforme a seção 6.2.

### 7.4 Não consigo acessar o painel de administração

1. Confirme que o dispositivo está conectado à rede do roteador, e não aos dados móveis.
2. Digite o endereço completo http://192.168.10.1 na barra de endereços, e não no campo de busca.
3. Se o roteador estiver em modo ponto de acesso, use http://tucano.local.
4. Limpe o cache do navegador ou use uma janela anônima.
5. Se o painel informar bloqueio por tentativas incorretas, aguarde 15 minutos.

### 7.5 Esqueci a senha

Se você esqueceu a senha do Wi-Fi, acesse o painel de administração com um dispositivo conectado por cabo e veja ou altere a senha em Wi-Fi, opção Rede principal.

Se você esqueceu a senha de administração, não há como recuperá-la: é necessário fazer a restauração de fábrica descrita na seção 6.3 e configurar o roteador novamente.

### 7.6 Um dispositivo não conecta ao Wi-Fi

- Confira se a senha foi digitada corretamente, respeitando maiúsculas e minúsculas.
- No dispositivo, escolha a opção Esquecer esta rede e conecte novamente.
- Se o dispositivo for antigo, altere a segurança para o modo misto WPA2/WPA3, conforme a seção 5.2.
- Verifique se o limite de 64 dispositivos foi atingido e se o filtro de MAC não está bloqueando o aparelho.
- Dispositivos que só funcionam em 2,4 GHz exigem a desativação da Conexão Inteligente, conforme a seção 3.2.

### 7.7 Códigos de erro do painel

- E101: sem sinal na porta WAN. Verifique o cabo e o modem.
- E102: falha de autenticação PPPoE. Verifique o usuário e a senha fornecidos pela operadora.
- E103: conflito de endereço IP entre o modem e o roteador. Altere a rede local conforme a seção 4.2.
- E201: falha ao baixar a atualização de firmware. Verifique a conexão e tente novamente após 10 minutos.
- E202: arquivo de firmware inválido ou corrompido. Baixe o arquivo novamente.
- E301: temperatura interna acima do limite. Desligue o roteador por 15 minutos e melhore a ventilação.

### 7.8 Recuperação após falha de atualização

1. Desligue o roteador pelo botão liga/desliga.
2. Mantenha o botão RESET pressionado e ligue o roteador.
3. Continue pressionando por 15 segundos, até o LED Power piscar em laranja rapidamente.
4. Conecte um computador a uma porta LAN e configure nele o endereço IP fixo 192.168.10.50.
5. Acesse http://192.168.10.1 e envie o arquivo de firmware baixado da página de suporte.
6. Aguarde cerca de 5 minutos sem desligar o equipamento.

## 8 Rede mesh

### 8.1 Adicionar uma unidade mesh

Até 4 unidades adicionais podem ser ligadas a um roteador principal para ampliar a cobertura.

1. Ligue a nova unidade na tomada, no mesmo cômodo do roteador principal, e aguarde o LED Power ficar verde fixo.
2. Pressione o botão WPS do roteador principal por 2 segundos e, em até 2 minutos, pressione o botão WPS da nova unidade.
3. Aguarde o LED Mesh da nova unidade ficar branco fixo, o que leva até 3 minutos.
4. Desligue a unidade e leve-a para o local definitivo.

### 8.2 Posicionamento das unidades

Posicione cada unidade a no máximo dois cômodos, ou cerca de 10 metros, de outra unidade. Use o LED Mesh como referência: branco indica posição adequada, amarelo indica que a unidade está longe demais e vermelho indica que ela perdeu a conexão. Quando houver cabo de rede disponível, ligue as unidades por cabo entre portas LAN: o roteador detecta a ligação automaticamente e a rede fica mais rápida.

## 9 Garantia e suporte

### 9.1 Garantia

O produto tem garantia de 12 meses contra defeitos de fabricação, contados a partir da data da nota fiscal, já incluída a garantia legal de 90 dias. A garantia não cobre danos causados por descargas elétricas, líquidos, quedas, instalação em local inadequado ou firmware não oficial.

### 9.2 Canais de atendimento

Antes de entrar em contato, anote o número de série impresso na etiqueta da base e a versão de firmware exibida em Sistema, opção Sobre.

- Central de ajuda: https://ajuda.tucano.example
- E-mail: suporte@tucano.example
- Telefone: 0800 000 1234, de segunda a sexta-feira, das 8h às 20h
- Downloads de firmware: https://ajuda.tucano.example/downloads

### 9.3 Descarte

Não descarte o roteador no lixo comum. Leve o equipamento a um ponto de coleta de resíduos eletrônicos.
