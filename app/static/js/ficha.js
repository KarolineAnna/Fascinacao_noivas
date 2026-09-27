/* Ficha de aluguel: seleção de peças, cálculo financeiro e busca de cliente pelo CPF. */
(function () {
  "use strict";

  var F = window.Fascinacao;
  var config = JSON.parse(document.getElementById("dados-ficha").textContent);
  var catalogo = {};
  config.catalogo.forEach(function (p) { catalogo[p.id] = p; });

  var $ = function (id) { return document.getElementById(id); };
  var tbody = $("itens");
  var busca = $("busca-peca");
  var sugestoes = $("sugestoes");

  // --- Dinheiro ---------------------------------------------------------------

  function paraCentavos(texto) {
    var s = (texto || "").replace(/R\$|\s/g, "");
    if (!s) return 0;
    if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", ".");
    else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");  // "1.200" = mil e duzentos
    var n = parseFloat(s);
    return isNaN(n) || n < 0 ? 0 : Math.round(n * 100);
  }

  function brl(centavos) {
    var neg = centavos < 0;
    centavos = Math.abs(centavos);
    var inteiro = Math.floor(centavos / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    var resto = ("0" + (centavos % 100)).slice(-2);
    return (neg ? "-" : "") + "R$ " + inteiro + "," + resto;
  }

  var ROTULOS = { alugada: "Alugada", lavagem: "Em lavagem" };

  function dataBr(iso) { return iso ? iso.split("-").reverse().join("/") : ""; }

  function aviso(p) {
    if (p.situacao === "lavagem")
      return "Em lavagem desde " + dataBr(p.lavagem_desde) + ": confira se estará pronta até a saída.";
    if (p.situacao === "alugada") return "Alugada no momento (ainda não devolvida).";
    return "";
  }

  function normalizar(t) {
    return (t || "").toString().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  // --- Itens --------------------------------------------------------------------

  function idsNaFicha() {
    return Array.prototype.map.call(tbody.querySelectorAll("input[name=produto_id]"),
      function (i) { return i.value; });
  }

  function adicionarItem(produtoId, valor) {
    var p = catalogo[produtoId];
    if (!p || idsNaFicha().indexOf(String(produtoId)) >= 0) return;

    var tr = document.createElement("tr");
    var detalhes = [p.tipo, p.tamanho && "Tam. " + p.tamanho, p.cor].filter(Boolean).join(" · ");
    tr.innerHTML =
      '<td><span class="codigo"></span><span class="principal nome"></span>' +
      '<div class="suave pequeno detalhes"></div>' +
      '<div class="pequeno aviso-peca"></div>' +
      '<input type="hidden" name="produto_id"></td>' +
      '<td class="direita"><input type="text" name="valor_cobrado" inputmode="decimal"></td>' +
      '<td class="direita"><button type="button" class="btn btn-sm btn-texto btn-perigo">Remover</button></td>';
    tr.querySelector(".codigo").textContent = p.codigo;
    tr.querySelector(".nome").textContent = p.nome;
    tr.querySelector(".detalhes").textContent = detalhes;
    tr.querySelector(".aviso-peca").textContent = aviso(p);
    tr.querySelector("input[name=produto_id]").value = p.id;
    var campoValor = tr.querySelector("input[name=valor_cobrado]");
    campoValor.value = valor != null ? valor : p.valor;
    campoValor.addEventListener("input", recalcular);
    tr.querySelector("button").addEventListener("click", function () { tr.remove(); recalcular(); });
    tbody.appendChild(tr);
    recalcular();
  }

  // --- Busca de peças -----------------------------------------------------------

  var selecionada = -1;

  function mostrarSugestoes() {
    var termo = normalizar(busca.value.trim());
    var usados = idsNaFicha();
    var lista = config.catalogo.filter(function (p) {
      if (usados.indexOf(String(p.id)) >= 0) return false;
      if (!termo) return true;
      return normalizar([p.codigo, p.nome, p.tipo, p.cor, p.tamanho].join(" ")).indexOf(termo) >= 0;
    }).slice(0, 30);

    sugestoes.innerHTML = "";
    selecionada = -1;
    if (!lista.length) {
      var li = document.createElement("li");
      li.className = "nada";
      li.textContent = config.catalogo.length ? "Nenhuma peça encontrada." : "Nenhuma peça cadastrada ainda.";
      sugestoes.appendChild(li);
      if (busca.value.trim()) {
        var novo = document.createElement("li");
        novo.className = "cadastrar";
        novo.dataset.cadastrar = "1";
        novo.innerHTML = '<span>+ Cadastrar novo produto <span class="termo"></span></span>';
        novo.querySelector(".termo").textContent = "“" + busca.value.trim() + "”";
        novo.addEventListener("mousedown", function (e) { e.preventDefault(); abrirCadastro(busca.value.trim()); });
        sugestoes.appendChild(novo);
      }
    }
    lista.forEach(function (p) {
      var li = document.createElement("li");
      li.dataset.id = p.id;
      li.innerHTML = '<span><span class="codigo"></span><span class="nome"></span> ' +
        '<span class="suave pequeno det"></span> <span class="selo-peca"></span></span>' +
        '<span class="num suave">R$ <b></b></span>';
      if (ROTULOS[p.situacao]) {
        var s = li.querySelector(".selo-peca");
        s.className = "selo selo-peca-" + p.situacao;
        s.textContent = ROTULOS[p.situacao];
      }
      li.querySelector(".codigo").textContent = p.codigo;
      li.querySelector(".nome").textContent = p.nome;
      li.querySelector(".det").textContent = [p.tamanho, p.cor].filter(Boolean).join(" · ");
      li.querySelector("b").textContent = p.valor;
      li.addEventListener("mousedown", function (e) { e.preventDefault(); escolher(p.id); });
      sugestoes.appendChild(li);
    });
    sugestoes.hidden = false;
  }

  function escolher(id) {
    adicionarItem(id);
    busca.value = "";
    sugestoes.hidden = true;
    busca.focus();
  }

  busca.addEventListener("input", mostrarSugestoes);
  busca.addEventListener("focus", mostrarSugestoes);
  busca.addEventListener("blur", function () { sugestoes.hidden = true; });
  busca.addEventListener("keydown", function (e) {
    var itens = sugestoes.querySelectorAll("li[data-id]");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!itens.length) return;
      selecionada = (selecionada + (e.key === "ArrowDown" ? 1 : -1) + itens.length) % itens.length;
      itens.forEach(function (li, i) { li.classList.toggle("ativo", i === selecionada); });
      itens[selecionada].scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      var alvo = itens[selecionada >= 0 ? selecionada : 0];
      if (alvo) escolher(alvo.dataset.id);
      else if (sugestoes.querySelector("[data-cadastrar]")) abrirCadastro(busca.value.trim());
    } else if (e.key === "Escape") {
      sugestoes.hidden = true;
    }
  });

  // --- Cadastro rápido de produto (sem sair da ficha) -------------------------------

  function abrirCadastro(texto) {
    var esc = window.Janela.esc;
    sugestoes.hidden = true;
    var tipos = config.tipos.map(function (t) { return "<option>" + esc(t) + "</option>"; }).join("");
    window.Janela.abrir({
      sobretitulo: "Produtos",
      titulo: "Cadastrar novo produto",
      rotuloConfirmar: "Salvar peça",
      larga: true,
      corpo:
        '<p class="modal-texto">A peça entra no cadastro de produtos, com código gerado automaticamente, ' +
          'e já fica selecionada nesta ficha.</p>' +
        '<div class="campos modal-campos">' +
          '<div class="campo c-12"><label>Nome / descrição <span class="obrigatorio">*</span></label>' +
            '<input type="text" name="nome" value="' + esc(texto) + '" autofocus></div>' +
          '<div class="campo c-4"><label>Tipo</label><select name="tipo"><option value="">—</option>' + tipos + "</select></div>" +
          '<div class="campo c-4"><label>Tamanho</label><input type="text" name="tamanho" placeholder="Ex.: 40, M, 52"></div>' +
          '<div class="campo c-4"><label>Cor</label><input type="text" name="cor" placeholder="Ex.: Off-white"></div>' +
          '<div class="campo c-4"><label>Valor do aluguel (R$) <span class="obrigatorio">*</span></label>' +
            '<input type="text" name="valor_aluguel" inputmode="decimal" placeholder="0,00"></div>' +
        "</div>",
      validar: function (c) {
        var falta = [];
        if (!c.querySelector("[name=nome]").value.trim()) falta.push("Informe o nome ou a descrição da peça.");
        if (!c.querySelector("[name=valor_aluguel]").value.trim()) falta.push("Informe o valor do aluguel.");
        return falta.length ? falta : "";
      },
      aoConfirmar: function (c) {
        return fetch(config.apiNovoProduto, { method: "POST", body: new FormData(c) })
          .then(function (r) { return r.json(); })
          .then(function (res) {
            if (!res.ok) return res.erros;
            config.catalogo.push(res.produto);
            catalogo[res.produto.id] = res.produto;
            adicionarItem(res.produto.id);
            busca.value = "";
            return "";
          });
      },
      aoCancelar: function () { busca.focus(); }
    });
  }

  // --- Pagamento e resumo ----------------------------------------------------------

  var entradaPaga = $("entrada_paga");
  var restantePago = $("restante_pago");

  function recalcular() {
    var valores = tbody.querySelectorAll("input[name=valor_cobrado]");
    var total = 0;
    valores.forEach(function (i) { total += paraCentavos(i.value); });
    var entrada = entradaPaga.checked ? paraCentavos($("valor_entrada").value) : 0;
    var restante = total - entrada;

    var status = "entrada_pendente";
    if (restantePago.checked || (total > 0 && restante <= 0)) status = "quitada";
    else if (entradaPaga.checked) status = "entrada_paga";

    $("resumo-qtd").textContent = valores.length;
    $("resumo-total").textContent = brl(total);
    $("resumo-entrada").textContent = brl(entrada);
    $("resumo-restante").textContent = brl(Math.max(restante, 0));
    $("restante-rotulo").textContent = brl(Math.max(restante, 0));
    var selo = $("resumo-status");
    selo.className = "selo selo-" + status;
    selo.textContent = config.status[status];

    $("valor_entrada").classList.toggle("invalido", entradaPaga.checked && entrada > total && total > 0);
    $("sem-itens").hidden = valores.length > 0;
    $("tabela-itens").hidden = valores.length === 0;
  }

  function alternar(check, detalhe) {
    check.addEventListener("change", function () {
      $(detalhe).hidden = !check.checked;
      recalcular();
    });
  }
  alternar(entradaPaga, "detalhe-entrada");
  alternar(restantePago, "detalhe-restante");
  $("valor_entrada").addEventListener("input", recalcular);

  // --- Datas -----------------------------------------------------------------------

  var saida = $("data_saida"), devolucao = $("data_devolucao");
  function validarDatas() {
    var ruim = saida.value && devolucao.value && devolucao.value <= saida.value;
    $("datas-ajuda").hidden = !ruim;
    devolucao.classList.toggle("invalido", !!ruim);
    var fp = devolucao._flatpickr;   // calendário do sistema (datas.js)
    if (fp) fp.altInput.classList.toggle("invalido", !!ruim);
    if (saida.value) {
      var d = new Date(saida.value + "T12:00:00");
      d.setDate(d.getDate() + 1);
      var minimo = d.toISOString().slice(0, 10);
      if (fp) fp.set("minDate", minimo); else devolucao.min = minimo;
    }
  }
  saida.addEventListener("change", validarDatas);
  devolucao.addEventListener("change", validarDatas);

  // --- Cliente pelo CPF ---------------------------------------------------------------

  var cpf = $("cpf"), ajuda = $("cpf-ajuda"), ultimaBusca = "";
  var textoPadrao = ajuda.textContent;

  function mensagemCpf(texto, classe) {
    ajuda.textContent = texto;
    ajuda.className = "ajuda" + (classe ? " " + classe : "");
  }

  cpf.addEventListener("input", function () {
    var d = F.digitos(cpf.value);
    cpf.classList.remove("invalido");
    if (d.length < 11) { ultimaBusca = ""; mensagemCpf(textoPadrao); return; }
    if (!F.cpfValido(d)) {
      cpf.classList.add("invalido");
      mensagemCpf("CPF inválido. Confira os números.", "erro");
      return;
    }
    if (d === ultimaBusca) return;
    ultimaBusca = d;
    fetch(config.apiCpf.replace("CPF", d))
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.cliente) {
          $("nome").value = res.cliente.nome;
          $("telefone").value = res.cliente.telefone;
          $("endereco").value = res.cliente.endereco;
          mensagemCpf("Cliente já cadastrado: dados preenchidos.", "ok");
        } else {
          mensagemCpf("CPF válido. Novo cliente será cadastrado.", "ok");
        }
      })
      .catch(function () { mensagemCpf(textoPadrao); });
  });

  // --- Início -------------------------------------------------------------------------

  config.itens.forEach(function (i) { adicionarItem(i.produto_id, i.valor); });
  recalcular();
  validarDatas();
})();
