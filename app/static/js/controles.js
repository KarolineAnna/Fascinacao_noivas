/* Interruptores da ficha com janela de confirmação:
   entrada paga, retirada, restante pago, devolvida, caução recebida, caução devolvida e multa paga.

   Cada controle é um checkbox ou botão com data-controle="<campo>" dentro de um elemento com
   data-ficha-url (rota /fichas/<id>/controle) e, opcionalmente:
     data-restante ("R$ 800,00"), data-restante-pago="1", data-total, data-voltar,
     data-atraso-dias, data-multa ("150,00"), data-multa-texto, data-caucao ("200,00" em aberto),
     data-multa-valor ("150,00" já calculada).
   Botões usam data-ligar="1|0"; checkboxes usam o novo estado marcado. */
(function () {
  "use strict";

  var cfgEl = document.getElementById("dados-controles");
  var cfg = cfgEl ? JSON.parse(cfgEl.textContent) : { formas: [], hoje: "" };

  var esc = window.Janela.esc;
  var abrir = window.Janela.abrir;

  /* Bloco de valor (opcional) + forma + data. Com prefixo, os nomes viram prefixo_forma etc.,
     para caber mais de um bloco na mesma janela. */
  function camposPagamento(comValor, prefixo, valorInicial, rotuloValor, rotuloForma) {
    var n = function (k) { return prefixo ? prefixo + "_" + k : k; };
    var opcoes = cfg.formas.map(function (f) { return "<option>" + esc(f) + "</option>"; }).join("");
    var largura = comValor ? "c-4" : "c-6";
    return '<div class="campos modal-campos">' +
      (comValor ? '<div class="campo c-4"><label>' + esc(rotuloValor || "Valor (R$)") + "</label>" +
        '<input type="text" name="valor" inputmode="decimal" placeholder="0,00" value="' +
        esc(valorInicial || "") + '"></div>' : "") +
      '<div class="campo ' + largura + '"><label>' + esc(rotuloForma || "Forma de pagamento") + ' <span class="obrigatorio">*</span></label>' +
        '<select name="' + n("forma") + '"><option value="">Selecione…</option>' + opcoes + "</select></div>" +
      '<div class="campo ' + largura + '"><label>Data</label>' +
        '<input type="date" name="' + n("data") + '" value="' + esc(cfg.hoje) + '"></div>' +
      "</div>";
  }

  function caixa(nome, texto, valorLado) {
    return '<label class="caixa-selecao modal-pergunta">' +
      '<input type="checkbox" name="' + nome + '" value="1">' +
      '<span class="caixa-marca" aria-hidden="true"></span>' +
      '<span class="texto">' + esc(texto) + "</span>" +
      (valorLado ? '<span class="num valor-lado">' + esc(valorLado) + "</span>" : "") +
      "</label>";
  }

  function detalhe(nome, html) {
    return '<div class="modal-detalhe" data-de="' + nome + '" hidden>' + html + "</div>";
  }

  // mostra o bloco de cada caixa de seleção quando ela é marcada
  function ligarCaixas(c) {
    c.querySelectorAll(".modal-detalhe[data-de]").forEach(function (bloco) {
      var chk = c.querySelector('[name="' + bloco.dataset.de + '"]');
      chk.addEventListener("change", function () { bloco.hidden = !chk.checked; });
    });
  }

  // --- Envio ----------------------------------------------------------------------------

  function enviar(url, dados, voltar) {
    var form = document.createElement("form");
    form.method = "post";
    form.action = url;
    form.hidden = true;
    if (voltar) dados.voltar = voltar;
    Object.keys(dados).forEach(function (k) {
      var i = document.createElement("input");
      i.type = "hidden"; i.name = k; i.value = dados[k];
      form.appendChild(i);
    });
    document.body.appendChild(form);
    form.submit();
  }

  function valorDe(corpo, nome) {
    var el = corpo.querySelector('[name="' + nome + '"]');
    return el ? el.value.trim() : "";
  }

  function marcado(corpo, nome) {
    var el = corpo.querySelector('[name="' + nome + '"]');
    return !!(el && el.checked);
  }

  function exigirPagamento(corpo, prefixo, oque) {
    var p = prefixo ? prefixo + "_" : "";
    if (!valorDe(corpo, p + "forma")) return "Escolha a forma de pagamento" + (oque ? " " + oque : "") + ".";
    if (!valorDe(corpo, p + "data")) return "Informe a data" + (oque ? " " + oque : "") + ".";
    return "";
  }

  // todos os campos da janela (checkbox vira "1"/"0"); campos de data usam o valor aaaa-mm-dd
  function coletar(corpo) {
    var dados = {};
    corpo.querySelectorAll("[name]").forEach(function (el) {
      dados[el.name] = el.type === "checkbox" ? (el.checked ? "1" : "0") : el.value.trim();
    });
    return dados;
  }

  // --- Textos -----------------------------------------------------------------------------

  var TEXTOS = {
    entrada: { sim: "Você gostaria de marcar a entrada como paga?", nao: "Você gostaria de desmarcar a entrada como paga?",
               notaNao: "O recebimento da entrada será retirado do financeiro." },
    restante: { sim: "Você gostaria de marcar o restante como pago?", nao: "Você gostaria de desmarcar o restante como pago?",
                notaNao: "O recebimento do restante será retirado do financeiro." },
    retirada: { sim: "Você gostaria de marcar esta ficha como retirada?", nao: "Você gostaria de desmarcar esta ficha como retirada?",
                notaNao: "A ficha voltará para “Reservada”." },
    devolvida: { sim: "Você gostaria de marcar esta ficha como devolvida?", nao: "Você gostaria de desmarcar esta ficha como devolvida?",
                 notaSim: "As peças desta ficha irão para “Em lavagem”.",
                 notaNao: "A ficha voltará para “Retirada” e as peças sairão de “Em lavagem”. Uma multa ainda não paga é descartada." },
    caucao: { sim: "Você gostaria de registrar a caução?", nao: "Você gostaria de remover a caução desta ficha?",
              notaNao: "O recebimento da caução será retirado do financeiro." },
    caucao_devolvida: { sim: "Você gostaria de marcar a caução como devolvida?", nao: "Você gostaria de desmarcar a devolução da caução?",
                        notaNao: "A devolução da caução será retirada do financeiro." },
    multa: { sim: "Você gostaria de marcar a multa como paga?", nao: "Você gostaria de desmarcar o pagamento da multa?",
             notaNao: "O recebimento da multa será retirado do financeiro." },
    isentar_multa: { sim: "Você gostaria de isentar a multa por atraso?", notaSim: "A multa desta ficha passa a ser R$ 0,00." }
  };

  function nota(texto) { return texto ? '<p class="modal-texto">' + esc(texto) + "</p>" : ""; }

  function tratar(el, ligar, aoCancelar) {
    var d = el.closest("[data-ficha-url]").dataset;
    var campo = el.dataset.controle;
    var t = TEXTOS[campo];
    var opcoes = { titulo: ligar ? t.sim : t.nao, aoCancelar: aoCancelar };
    var restantePendente = d.restantePago !== "1" && d.restante && d.restante !== "R$ 0,00";
    var dias = parseInt(d.atrasoDias || "0", 10);

    if (campo === "entrada" && ligar) {
      opcoes.corpo = nota("Valor do aluguel: " + (d.total || "")) + camposPagamento(true);
      opcoes.validar = function (c) { return valorDe(c, "valor") ? exigirPagamento(c) : "Informe o valor da entrada."; };

    } else if (campo === "restante" && ligar) {
      opcoes.corpo = nota("Restante a receber: " + (d.restante || "")) + camposPagamento(false);
      opcoes.validar = function (c) { return exigirPagamento(c); };

    } else if (campo === "retirada" && ligar && restantePendente) {
      opcoes.corpo = caixa("restante_agora", "O restante foi pago agora", d.restante) +
        detalhe("restante_agora", camposPagamento(false));
      opcoes.validar = function (c) { return marcado(c, "restante_agora") ? exigirPagamento(c) : ""; };

    } else if (campo === "devolvida" && ligar) {
      var html = nota(t.notaSim);
      if (dias > 0) {
        html += '<div class="modal-alerta">Devolução com <strong>' + dias + " dia" + (dias > 1 ? "s" : "") +
          " de atraso</strong>. Multa: " + esc(d.multaTexto || "") + " por dia.</div>" +
          '<div class="campos modal-campos"><div class="campo c-6"><label>Multa por atraso (R$)</label>' +
          '<input type="text" name="multa_valor" inputmode="decimal" value="' + esc(d.multa || "") + '">' +
          '<div class="ajuda">Ajuste se precisar. Deixe 0,00 para isentar.</div></div></div>' +
          caixa("multa_agora", "A multa foi paga agora") +
          detalhe("multa_agora", camposPagamento(false, "multa"));
      }
      if (d.caucao) {
        html += caixa("caucao_agora", "Devolver a caução agora", "R$ " + d.caucao) +
          detalhe("caucao_agora",
            '<div class="campos modal-campos"><div class="campo c-12"><label>Valor devolvido (R$)</label>' +
            '<input type="text" name="caucao_devolvido" inputmode="decimal" value="' + esc(d.caucao) + '">' +
            '<div class="ajuda">Se reter uma parte por danos, informe só o que será devolvido.</div></div></div>' +
            camposPagamento(false, "caucao", "", "", "Forma da devolução"));
      }
      opcoes.corpo = html;
      opcoes.validar = function (c) {
        return (marcado(c, "multa_agora") ? exigirPagamento(c, "multa", "da multa") : "") ||
               (marcado(c, "caucao_agora") ? exigirPagamento(c, "caucao", "da devolução da caução") : "");
      };

    } else if (campo === "caucao" && ligar) {
      opcoes.corpo = nota("Valor deixado pelo cliente como garantia. Ele é devolvido após a conferência das peças.") +
        camposPagamento(true, "", "", "Valor da caução (R$)");
      opcoes.validar = function (c) { return valorDe(c, "valor") ? exigirPagamento(c) : "Informe o valor da caução."; };

    } else if (campo === "caucao_devolvida" && ligar) {
      opcoes.corpo = nota("Caução recebida: R$ " + (d.caucao || "") + ". Se reter uma parte por danos, informe só o valor devolvido.") +
        camposPagamento(true, "", d.caucao, "Valor devolvido (R$)", "Forma da devolução");
      opcoes.validar = function (c) { return exigirPagamento(c); };

    } else if (campo === "multa" && ligar) {
      opcoes.corpo = nota("Multa por atraso desta ficha.") + camposPagamento(true, "", d.multaValor, "Valor da multa (R$)");
      opcoes.validar = function (c) { return valorDe(c, "valor") ? exigirPagamento(c) : "Informe o valor da multa."; };

    } else {
      opcoes.corpo = nota(ligar ? t.notaSim : t.notaNao);
    }

    opcoes.aoAbrir = ligarCaixas;
    opcoes.aoConfirmar = function (c) {
      var dados = coletar(c);
      dados.campo = campo;
      dados.ligar = ligar ? "1" : "0";
      enviar(d.fichaUrl, dados, d.voltar);
    };
    abrir(opcoes);
  }

  document.querySelectorAll("input[type=checkbox][data-controle]").forEach(function (chk) {
    chk.addEventListener("change", function () {
      var ligar = chk.checked;
      tratar(chk, ligar, function () { chk.checked = !ligar; });
    });
  });

  // Formulários simples que só precisam de confirmação: <form data-confirmar="Pergunta?" data-nota="...">
  document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (form.dataset.confirmado) return;
      e.preventDefault();
      if (!form.reportValidity()) return;
      abrir({
        titulo: form.dataset.confirmar,
        corpo: nota(form.dataset.nota),
        aoConfirmar: function () { form.dataset.confirmado = "1"; form.submit(); }
      });
    });
  });

  document.querySelectorAll("button[data-controle]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.preventDefault();
      tratar(btn, btn.dataset.ligar === "1");
    });
  });
})();
