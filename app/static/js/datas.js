/* Calendário do sistema (flatpickr, arquivos locais em static/vendor) no lugar do seletor padrão.

   - Todo <input type="date"> e <input type="month"> vira um calendário em português,
     com a semana começando no domingo.
   - Mostra dd/mm/aaaa (mês: "setembro de 2026"), mas o campo original continua enviando
     aaaa-mm-dd (ou aaaa-mm) ao servidor, como antes.
   - A data também pode ser digitada: dd/mm/aaaa (as barras entram sozinhas).
   - Campos criados depois (ex.: dentro das janelas) usam Datas.aplicar(elemento). */
(function () {
  "use strict";
  if (!window.flatpickr) return;

  var pt = Object.assign({}, window.flatpickr.l10ns.pt, { firstDayOfWeek: 0 });

  function mascara(e) {
    var campo = e.target;
    var d = campo.value.replace(/\D/g, "").slice(0, 8);
    var v = d.length > 4 ? d.slice(0, 2) + "/" + d.slice(2, 4) + "/" + d.slice(4)
          : d.length > 2 ? d.slice(0, 2) + "/" + d.slice(2) : d;
    if (v !== campo.value) campo.value = v;
  }

  function aplicar(raiz) {
    (raiz || document).querySelectorAll("input[type=date], input[type=month]").forEach(function (el) {
      if (el._flatpickr) return;
      var mes = el.type === "month";
      var opcoes = {
        locale: pt,
        altInput: true,
        altInputClass: "campo-data" + (mes ? " campo-mes" : ""),
        allowInput: !mes,
        disableMobile: true,
        dateFormat: mes ? "Y-m" : "Y-m-d",
        altFormat: mes ? "F \\d\\e Y" : "d/m/Y",
        minDate: el.min || null,
        maxDate: el.max || null,
        onReady: function (_d, _s, fp) {
          fp.altInput.placeholder = mes ? "Escolha o mês" : "dd/mm/aaaa";
          if (el.getAttribute("aria-label")) fp.altInput.setAttribute("aria-label", el.getAttribute("aria-label"));
          // o rótulo do campo passa a focar o campo visível
          if (el.id) {
            document.querySelectorAll('label[for="' + el.id + '"]').forEach(function (rotulo) {
              rotulo.addEventListener("click", function (ev) { ev.preventDefault(); fp.altInput.focus(); });
            });
          }
        }
      };
      if (mes && window.monthSelectPlugin) {
        opcoes.plugins = [new window.monthSelectPlugin({ shorthand: false, dateFormat: "Y-m", altFormat: "F \\d\\e Y" })];
      }
      el.type = "text";   // o flatpickr cuida do campo; o valor continua no formato do servidor
      var fp = window.flatpickr(el, opcoes);
      if (!mes) {
        fp.altInput.addEventListener("input", mascara);
        fp.altInput.setAttribute("inputmode", "numeric");
        fp.altInput.setAttribute("maxlength", "10");
      }
    });
  }

  aplicar();
  window.Datas = { aplicar: aplicar };
})();
