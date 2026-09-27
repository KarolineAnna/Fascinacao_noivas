/* Botão "Voltar" padronizado e aviso de alterações não salvas.

   Voltar: cada aba guarda o caminho percorrido (sessionStorage). Telas já visitadas não se
   repetem (voltar a uma tela corta o caminho até ela, e filtros da mesma tela não criam passos).
   Depois de enviar um formulário, a tela do formulário sai do caminho, para o Voltar não
   levar de novo a um formulário já salvo. Sem caminho conhecido, usa o destino padrão do link.

   Alterações não salvas: formulários com data-rastrear. Ao sair por um link do sistema com
   alterações, aparece a janela de confirmação do sistema; ao fechar/recarregar a aba,
   o aviso do próprio navegador. */
(function () {
  "use strict";

  var CHAVE = "fascinacao-caminho";
  var ENVIO = "fascinacao-enviando";
  var VOLTANDO = "fascinacao-voltando";

  function ler() {
    try { return JSON.parse(sessionStorage.getItem(CHAVE)) || []; } catch (e) { return []; }
  }
  function gravar(caminho) {
    try { sessionStorage.setItem(CHAVE, JSON.stringify(caminho.slice(-30))); } catch (e) { /* sem armazenamento */ }
  }

  var aqui = { caminho: location.pathname, url: location.pathname + location.search };
  var pilha = ler();

  // Chegou aqui depois de enviar um formulário: tira o formulário do caminho.
  var enviado = null;
  try { enviado = sessionStorage.getItem(ENVIO); sessionStorage.removeItem(ENVIO); } catch (e) { /* ignora */ }
  if (enviado && enviado !== aqui.caminho && pilha.length && pilha[pilha.length - 1].caminho === enviado) {
    pilha.pop();
  }

  // Chegou pelo Voltar (do sistema ou do navegador)?
  var voltando = false;
  try { voltando = sessionStorage.getItem(VOLTANDO) === "1"; sessionStorage.removeItem(VOLTANDO); } catch (e) { /* ignora */ }
  var tipo = performance.getEntriesByType && performance.getEntriesByType("navigation")[0];
  if (tipo && tipo.type === "back_forward") voltando = true;

  var indice = -1;
  pilha.forEach(function (p, i) { if (p.caminho === aqui.caminho) indice = i; });
  if (voltando && indice >= 0) {
    pilha = pilha.slice(0, indice);   // voltou: descarta o que veio depois desta tela
  } else if (indice >= 0) {
    pilha.splice(indice, 1);          // abriu de novo por outro caminho: a tela vai para o topo
  }
  pilha.push(aqui);                   // mesma tela com outros filtros só atualiza o endereço
  gravar(pilha);

  // --- Alterações não salvas -----------------------------------------------------

  var formularios = Array.prototype.slice.call(document.querySelectorAll("form[data-rastrear]"));
  var inicial = [];
  var liberado = false;

  function estado(form) {
    var partes = [];
    new FormData(form).forEach(function (v, k) { partes.push(k + "=" + v); });
    return partes.join("&");
  }

  window.addEventListener("load", function () {
    inicial = formularios.map(estado);   // depois dos scripts da tela montarem o formulário
  });

  function alterado() {
    if (liberado) return false;
    return formularios.some(function (f, i) {
      return f.dataset.alterado === "1" || (inicial[i] !== undefined && estado(f) !== inicial[i]);
    });
  }

  document.addEventListener("submit", function (e) {
    if (e.target.hasAttribute && e.target.hasAttribute("data-rastrear")) {
      liberado = true;
      try { sessionStorage.setItem(ENVIO, aqui.caminho); } catch (err) { /* ignora */ }
    }
  }, true);

  window.addEventListener("beforeunload", function (e) {
    if (alterado()) { e.preventDefault(); e.returnValue = ""; }
  });

  function sairPara(url, eVoltar) {
    function ir() {
      liberado = true;
      if (eVoltar) { try { sessionStorage.setItem(VOLTANDO, "1"); } catch (e) { /* ignora */ } }
      location.href = url;
    }
    if (!alterado()) { ir(); return; }
    window.Janela.abrir({
      sobretitulo: "Alterações não salvas",
      titulo: "Você tem alterações não salvas. Deseja sair mesmo assim?",
      corpo: '<p class="modal-texto">O que foi preenchido nesta tela será perdido.</p>',
      rotuloConfirmar: "Sair sem salvar",
      aoConfirmar: ir
    });
  }

  // --- Voltar ----------------------------------------------------------------------

  document.querySelectorAll("[data-voltar-app]").forEach(function (link) {
    link.addEventListener("click", function (e) {
      e.preventDefault();
      var anterior = pilha.length > 1 ? pilha[pilha.length - 2].url : link.getAttribute("href");
      sairPara(anterior, true);
    });
  });

  // Outros links internos (menu, logotipo, cancelar...) também avisam das alterações.
  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a[href]") : null;
    if (!a || a.hasAttribute("data-voltar-app") || a.target === "_blank" || e.defaultPrevented) return;
    if (a.origin !== location.origin || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (alterado()) { e.preventDefault(); sairPara(a.href); }
  });
})();
