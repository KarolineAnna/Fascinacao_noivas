/* Janela (modal) no estilo do sistema, usada no lugar dos alertas do navegador.

   Janela.abrir({
     titulo, sobretitulo ("Confirmação"), corpo (HTML), rotuloConfirmar ("Confirmar"), larga (bool),
     aoAbrir(corpo), validar(corpo) -> "mensagem de erro" | "",
     aoConfirmar(corpo) -> nada, ou uma Promise que resolve com "mensagem de erro" (mantém aberta) ou "",
     aoCancelar()
   }) */
(function () {
  "use strict";

  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var fundo = document.createElement("div");
  fundo.className = "modal-fundo";
  fundo.hidden = true;
  fundo.innerHTML =
    '<div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-titulo">' +
      '<div class="modal-sobre"></div>' +
      '<h2 id="modal-titulo"></h2>' +
      '<div class="ornamento"><span></span></div>' +
      '<form class="modal-corpo" novalidate></form>' +
      '<div class="modal-erro" hidden></div>' +
      '<div class="modal-acoes">' +
        '<button type="button" class="btn btn-texto" data-acao="cancelar">Cancelar</button>' +
        '<button type="button" class="btn btn-primario" data-acao="confirmar">Confirmar</button>' +
      "</div>" +
    "</div>";
  document.body.appendChild(fundo);

  var caixa = fundo.querySelector(".modal");
  var sobre = fundo.querySelector(".modal-sobre");
  var titulo = fundo.querySelector("h2");
  var corpo = fundo.querySelector(".modal-corpo");
  var erro = fundo.querySelector(".modal-erro");
  var botao = fundo.querySelector("[data-acao=confirmar]");
  var atual = null;
  var ocupado = false;

  function mostrarErro(mensagem) {
    erro.innerHTML = "";
    [].concat(mensagem).forEach(function (m) {
      var linha = document.createElement("div");
      linha.textContent = m;
      erro.appendChild(linha);
    });
    erro.hidden = false;
  }

  function fechar(confirmado) {
    if (ocupado) return;
    fundo.hidden = true;
    document.body.classList.remove("modal-aberto");
    var a = atual;
    atual = null;
    if (a && !confirmado && a.aoCancelar) a.aoCancelar();
  }

  function abrir(opcoes) {
    atual = opcoes;
    sobre.textContent = opcoes.sobretitulo || "Confirmação";
    titulo.textContent = opcoes.titulo;
    botao.textContent = opcoes.rotuloConfirmar || "Confirmar";
    caixa.classList.toggle("modal-larga", !!opcoes.larga);
    corpo.innerHTML = opcoes.corpo || "";
    if (window.Datas) window.Datas.aplicar(corpo);   // campos de data dentro da janela
    erro.hidden = true;
    fundo.hidden = false;
    document.body.classList.add("modal-aberto");
    if (opcoes.aoAbrir) opcoes.aoAbrir(corpo);
    var foco = corpo.querySelector("[autofocus]") ||
      corpo.querySelector("input:not([type=hidden]):not([type=checkbox]), select");
    (foco || botao).focus();
  }

  function confirmar() {
    if (!atual || ocupado) return;
    var mensagem = atual.validar ? atual.validar(corpo) : "";
    if (mensagem) { mostrarErro(mensagem); return; }
    var resultado = atual.aoConfirmar(corpo);
    if (resultado && typeof resultado.then === "function") {
      ocupado = true;
      botao.disabled = true;
      resultado.then(function (msg) {
        ocupado = false;
        botao.disabled = false;
        if (msg && msg.length) mostrarErro(msg); else fechar(true);
      }, function () {
        ocupado = false;
        botao.disabled = false;
        mostrarErro("Não foi possível salvar. Tente novamente.");
      });
    } else {
      fechar(true);
    }
  }

  fundo.addEventListener("click", function (e) {
    var acao = e.target.getAttribute("data-acao");
    if (acao === "cancelar" || e.target === fundo) fechar(false);
    if (acao === "confirmar") confirmar();
  });
  corpo.addEventListener("submit", function (e) { e.preventDefault(); confirmar(); });
  corpo.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.tagName === "INPUT" && e.target.type !== "checkbox") {
      e.preventDefault();
      confirmar();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (!fundo.hidden && e.key === "Escape") fechar(false);
  });

  window.Janela = { abrir: abrir, esc: esc };
})();
