// Banco de roteiros: usado quando a IA está desligada (sem chave) ou falha.
// Escolhe pelo tema informado (busca por palavra) ou faz rodízio pelo dia do ano.
const banco = [
  {
    tema: "nota fiscal",
    gancho: "Seu time ainda digita nota fiscal à mão?",
    cenas: [
      { texto: "O XML da NF-e já traz tudo pronto", narracao: "O XML da nota fiscal eletrônica já traz todos os dados prontos. Digitar é desperdício." },
      { texto: "Um robô confere com o pedido de compra", narracao: "Um robô lê o XML e confere item a item com o pedido de compra e com o que chegou no almoxarifado." },
      { texto: "Só as exceções chegam para você", narracao: "Você só olha as exceções: preço diferente, quantidade a mais ou nota duplicada." },
    ],
    cta: "Quer o passo a passo? Siga para a parte 2!",
    hashtags: ["#automacao", "#rpa", "#financeiro", "#notafiscal", "#produtividade"],
  },
  {
    tema: "golpe do boleto",
    gancho: "Esse boleto parece certo. Mas é golpe.",
    cenas: [
      { texto: "Nome do fornecedor certo, CNPJ errado", narracao: "No golpe do boleto, o nome do fornecedor está certo, mas o CNPJ do beneficiário é de outra pessoa." },
      { texto: "A automação compara com o cadastro", narracao: "Uma automação simples compara o beneficiário com o cadastro de fornecedores antes de pagar." },
      { texto: "E valida os dígitos da linha digitável", narracao: "E ainda valida os dígitos verificadores da linha digitável e o valor do código de barras." },
    ],
    cta: "Salve este vídeo e mostre para o seu financeiro!",
    hashtags: ["#golpedoboleto", "#seguranca", "#financeiro", "#automacao", "#dica"],
  },
  {
    tema: "n8n",
    gancho: "Automatizei meu TikTok com n8n. Sem programar.",
    cenas: [
      { texto: "A IA escreve o roteiro", narracao: "Primeiro, uma IA escreve o roteiro com gancho, cenas e chamada para ação." },
      { texto: "O vídeo é montado sozinho", narracao: "Depois o vídeo é montado sozinho: narração, legendas e formato vertical." },
      { texto: "E publicado pela API oficial", narracao: "Por fim, o n8n publica pela API oficial do TikTok e registra tudo numa planilha." },
    ],
    cta: "Comenta 'n8n' que eu te mando o fluxo!",
    hashtags: ["#n8n", "#automacao", "#nocode", "#ia", "#tiktokdicas"],
  },
  {
    tema: "chão de fábrica",
    gancho: "Sua fábrica perde dinheiro em paradas que ninguém registra.",
    cenas: [
      { texto: "Operador manda áudio no WhatsApp", narracao: "O operador só manda um áudio no WhatsApp dizendo o que parou e por quê." },
      { texto: "A IA classifica a causa", narracao: "A inteligência artificial transcreve, classifica a causa e calcula o tempo parado." },
      { texto: "O gestor recebe o relatório do turno", narracao: "No fim do turno, o gestor recebe o relatório pronto, com as maiores perdas." },
    ],
    cta: "Siga para ver mais automações industriais!",
    hashtags: ["#industria", "#manufatura", "#automacao", "#ia", "#oee"],
  },
  {
    tema: "planilha",
    gancho: "3 tarefas de planilha que um robô faz por você.",
    cenas: [
      { texto: "1. Juntar relatórios de vários e-mails", narracao: "Um: juntar relatórios que chegam em vários e-mails numa planilha só." },
      { texto: "2. Conciliar extrato com contas a pagar", narracao: "Dois: conciliar o extrato do banco com o contas a pagar." },
      { texto: "3. Mandar alerta de vencimento", narracao: "Três: mandar alerta antes de cada vencimento, para nunca mais pagar juros." },
    ],
    cta: "Qual dessas você quer aprender? Comenta!",
    hashtags: ["#excel", "#planilha", "#automacao", "#rpa", "#produtividade"],
  },
];

const tema = ($json.tema || "").toString().trim();
const normalizar = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
let escolhido = tema
  ? banco.find((r) => normalizar(tema).includes(normalizar(r.tema)) || normalizar(r.tema).includes(normalizar(tema)))
  : null;
if (!escolhido) {
  const inicio = new Date(new Date().getFullYear(), 0, 0);
  const diaDoAno = Math.floor((Date.now() - inicio) / 86400000);
  escolhido = banco[diaDoAno % banco.length];
}
return [{ json: { ...escolhido, tema: tema || escolhido.tema, origem: "banco" } }];
