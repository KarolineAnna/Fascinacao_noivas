/* Nova venda: escolha de produtos com quantidade, total automático e cliente opcional. */
(function () {
  "use strict";

  var config = JSON.parse(document.getElementById("dados-venda").textContent);
  var catalogo = {};
  config.catalogo.forEach(function (p) { catalogo[p.id] = p; });

  var $ = function (id) { return document.getElementById(id); };
  var tbody = $("itens"), busca = $("busca-produto"), sugestoes = $("sugestoes");

  function brl(c) {
    return "R$ " + Math.floor(c / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + ("0" + (c % 100)).slice(-2);
  }
  function normalizar(t) {
    return (t || "").toString().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }
  function ids() {
    return Array.prototype.map.call(tbody.querySelectorAll("input[name=produto_id]"), function (i) { return i.value; });
  }

  function recalcular() {
    var total = 0, qtd = 0;
    tbody.querySelectorAll("tr").forEach(function (tr) {
      var p = catalogo[tr.dataset.id];
      var q = Math.max(parseInt(tr.querySelector("input[name=quantidade]").value, 10) || 0, 0);
      tr.querySelector(".subtotal").textContent = brl(p.preco * q);
      total += p.preco * q;
      qtd += q;
    });
    $("resumo-total").textContent = brl(total);
    $("resumo-qtd").textContent = qtd;
    $("sem-itens").hidden = tbody.children.length > 0;
    $("tabela-itens").hidden = tbody.children.length === 0;
  }

  function adicionar(id, quantidade) {
    var p = catalogo[id];
    if (!p) return;
    var existente = tbody.querySelector('tr[data-id="' + id + '"]');
    if (existente) {   // mesmo produto de novo: soma na quantidade
      var campo = existente.querySelector("input[name=quantidade]");
      campo.value = (parseInt(campo.value, 10) || 0) + 1;
      recalcular();
      return;
    }
    var tr = document.createElement("tr");
    tr.dataset.id = id;
    tr.innerHTML =
      '<td><span class="principal nome"></span><div class="suave pequeno cat"></div>' +
      '<input type="hidden" name="produto_id"></td>' +
      '<td class="direita num preco"></td>' +
      '<td class="centro"><div class="quantidade">' +
        '<button type="button" class="btn btn-sm btn-texto menos" aria-label="Diminuir">−</button>' +
        '<input type="text" name="quantidade" inputmode="numeric" aria-label="Quantidade">' +
        '<button type="button" class="btn btn-sm btn-texto mais" aria-label="Aumentar">+</button>' +
      "</div></td>" +
      '<td class="direita num subtotal"></td>' +
      '<td class="direita"><button type="button" class="btn btn-sm btn-texto btn-perigo remover">Remover</button></td>';
    tr.querySelector(".nome").textContent = p.nome;
    tr.querySelector(".cat").textContent = p.categoria;
    tr.querySelector(".preco").textContent = brl(p.preco);
    tr.querySelector("input[name=produto_id]").value = id;
    var qtd = tr.querySelector("input[name=quantidade]");
    qtd.value = quantidade || 1;
    qtd.addEventListener("input", function () { qtd.value = qtd.value.replace(/\D/g, ""); recalcular(); });
    tr.querySelector(".menos").addEventListener("click", function () {
      qtd.value = Math.max((parseInt(qtd.value, 10) || 1) - 1, 1); recalcular();
    });
    tr.querySelector(".mais").addEventListener("click", function () {
      qtd.value = (parseInt(qtd.value, 10) || 0) + 1; recalcular();
    });
    tr.querySelector(".remover").addEventListener("click", function () { tr.remove(); recalcular(); });
    tbody.appendChild(tr);
    recalcular();
  }

  // --- Busca de produtos ------------------------------------------------------------

  var selecionada = -1;
  function mostrar() {
    var termo = normalizar(busca.value.trim());
    var lista = config.catalogo.filter(function (p) {
      return !termo || normalizar(p.nome + " " + p.categoria).indexOf(termo) >= 0;
    }).slice(0, 30);
    sugestoes.innerHTML = "";
    selecionada = -1;
    if (!lista.length) {
      var li = document.createElement("li");
      li.className = "nada";
      li.textContent = config.catalogo.length ? "Nenhum produto encontrado." : "Nenhum produto cadastrado ainda (menu Produtos à venda).";
      sugestoes.appendChild(li);
    }
    lista.forEach(function (p) {
      var li = document.createElement("li");
      li.dataset.id = p.id;
      li.innerHTML = '<span><span class="nome"></span> <span class="suave pequeno cat"></span></span><span class="num suave"></span>';
      li.querySelector(".nome").textContent = p.nome;
      li.querySelector(".cat").textContent = p.categoria;
      li.querySelector(".num").textContent = brl(p.preco);
      if (ids().indexOf(String(p.id)) >= 0) li.querySelector(".cat").textContent += " · já na venda";
      li.addEventListener("mousedown", function (e) { e.preventDefault(); escolher(p.id); });
      sugestoes.appendChild(li);
    });
    sugestoes.hidden = false;
  }
  function escolher(id) { adicionar(id); busca.value = ""; sugestoes.hidden = true; busca.focus(); }

  busca.addEventListener("input", mostrar);
  busca.addEventListener("focus", mostrar);
  busca.addEventListener("blur", function () { sugestoes.hidden = true; });
  busca.addEventListener("keydown", function (e) {
    var itens = sugestoes.querySelectorAll("li[data-id]");
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!itens.length) return;
      selecionada = (selecionada + (e.key === "ArrowDown" ? 1 : -1) + itens.length) % itens.length;
      itens.forEach(function (li, i) { li.classList.toggle("ativo", i === selecionada); });
    } else if (e.key === "Enter") {
      e.preventDefault();
      var alvo = itens[selecionada >= 0 ? selecionada : 0];
      if (alvo) escolher(alvo.dataset.id);
    } else if (e.key === "Escape") {
      sugestoes.hidden = true;
    }
  });

  // --- Cliente opcional --------------------------------------------------------------

  var nome = $("cliente_nome"), clienteId = $("cliente_id"), ajuda = $("cliente-ajuda");
  function conferirCliente() {
    var achado = config.clientes.filter(function (c) { return normalizar(c.nome) === normalizar(nome.value.trim()); })[0];
    clienteId.value = achado ? achado.id : "";
    ajuda.textContent = !nome.value.trim() ? "Escolha um cliente cadastrado ou digite um nome."
      : achado ? "Cliente cadastrado · CPF " + achado.cpf : "Nome livre (sem cadastro).";
    ajuda.className = "ajuda" + (achado ? " ok" : "");
  }
  nome.addEventListener("input", conferirCliente);

  config.itens.forEach(function (i) { adicionar(i.produto_id, i.quantidade); });
  recalcular();
  if (nome.value) conferirCliente();
})();
