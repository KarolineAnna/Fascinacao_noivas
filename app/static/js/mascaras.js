/* Máscaras de CPF e telefone e utilitários compartilhados. */
(function () {
  "use strict";

  function digitos(v) { return (v || "").replace(/\D/g, ""); }

  function mascaraCpf(v) {
    var d = digitos(v).slice(0, 11);
    return d
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d{1,2})$/, ".$1-$2");
  }

  function mascaraTelefone(v) {
    var d = digitos(v).slice(0, 11);
    if (d.length <= 2) return d.length ? "(" + d : "";
    if (d.length <= 6) return "(" + d.slice(0, 2) + ") " + d.slice(2);
    if (d.length <= 10) return "(" + d.slice(0, 2) + ") " + d.slice(2, 6) + "-" + d.slice(6);
    return "(" + d.slice(0, 2) + ") " + d.slice(2, 7) + "-" + d.slice(7);
  }

  function cpfValido(cpf) {
    var d = digitos(cpf);
    if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
    for (var t = 9; t <= 10; t++) {
      var soma = 0;
      for (var i = 0; i < t; i++) soma += parseInt(d[i], 10) * (t + 1 - i);
      if (((soma * 10) % 11) % 10 !== parseInt(d[t], 10)) return false;
    }
    return true;
  }

  var mascaras = { cpf: mascaraCpf, telefone: mascaraTelefone };

  document.querySelectorAll("[data-mascara]").forEach(function (campo) {
    var fn = mascaras[campo.dataset.mascara];
    if (!fn) return;
    campo.addEventListener("input", function () { campo.value = fn(campo.value); });
  });

  window.Fascinacao = { digitos: digitos, cpfValido: cpfValido, mascaraCpf: mascaraCpf };
})();
