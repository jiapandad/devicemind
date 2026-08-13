// DeviceMind Web UI 交互逻辑
(function () {
  "use strict";

  var state = null;

  var TYPE_ICON = {
    light: "💡", climate: "🌡️", switch: "🪟", sensor: "📡",
    lock: "🔒", camera: "📷", vacuum: "🧹", media: "🔊", other: "📦",
  };
  var TYPE_LABEL = {
    light: "灯", climate: "空调/暖通", switch: "开关", sensor: "传感器",
    lock: "门锁", camera: "摄像头", vacuum: "扫地机", media: "影音", other: "其他",
  };

  // 示例说明书（添加设备页一键体验）
  var SAMPLES = {
    "智能台灯": "产品名称：智能 LED 台灯\n型号：TL-100\n\n功能说明：\n1. 开关：支持远程开关\n2. 亮度调节：1%-100% 无级调光\n3. 色温调节：2700K-6500K\n\n控制协议：MQTT\ntopic: smarthome/desklamp/set",
    "加湿器": "产品名称：智能加湿器\n型号：HM-200\n\n功能说明：\n1. 开关：支持远程开关\n2. 湿度档位：低/中/高 三档\n3. 水量监测：缺水提醒\n\n控制协议：MQTT\ntopic: smarthome/humidifier/set",
    "扫地机器人": "产品名称：智能扫地机器人\n型号：RV-300\n\n功能说明：\n1. 开关：开始/停止清扫\n2. 清扫模式：自动/定点/沿边\n3. 吸力档位：静音/标准/强力\n4. 电量监测：剩余电量百分比\n\n控制协议：MQTT\ntopic: smarthome/vacuum/set",
  };

  // ---------- 基础工具 ----------
  function $(sel) { return document.querySelector(sel); }
  function $all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function showToast(msg, type) {
    var t = $("#toast");
    t.textContent = msg;
    t.className = "toast show " + (type || "");
    clearTimeout(t._timer);
    t._timer = setTimeout(function () { t.className = "toast"; }, 2600);
  }

  function api(path, opts) {
    return fetch(path, opts).then(function (r) { return r.json(); });
  }

  // ---------- 状态加载与渲染 ----------
  function fetchState() {
    api("/api/state").then(function (j) {
      if (j.ok) {
        state = j.data;
        setStatus(true);
        render();
      } else {
        setStatus(false);
      }
    }).catch(function () { setStatus(false); });
  }

  function setStatus(ok) {
    $("#status-dot").className = "dot" + (ok ? "" : " off");
    $("#status-text").textContent = ok ? "已连接" : "连接失败";
  }

  function render() {
    renderDevices();
    renderScenes();
    renderAutomations();
    renderLinkages();
  }

  // ---------- 设备 ----------
  function renderDevices() {
    var grid = $("#devices-grid");
    if (!state.devices.length) {
      grid.innerHTML = '<div class="empty">还没有设备，去「添加设备」接入第一个吧</div>';
      return;
    }
    grid.innerHTML = state.devices.map(deviceCard).join("");
    bindDeviceEvents();
  }

  function deviceCard(d) {
    var icon = TYPE_ICON[d.type] || "📦";
    var typeLabel = TYPE_LABEL[d.type] || d.type;
    var stateChips = stateChipsHtml(d.state);
    var controls = deviceControls(d);
    return (
      '<div class="device-card" data-id="' + esc(d.id) + '">' +
        '<div class="device-head">' +
          '<div class="device-icon">' + icon + "</div>" +
          '<div><div class="device-name">' + esc(d.name) + "</div>" +
          '<div class="device-id">' + esc(d.id) + ' · <span class="device-type">' + esc(typeLabel) + "</span></div></div>" +
        "</div>" +
        '<div class="device-state">' + stateChips + "</div>" +
        '<div class="device-actions">' + controls + "</div>" +
        '<div class="text-command">' +
          '<input type="text" placeholder="说人话，如：调到 50%" data-cmd-input>' +
          '<button class="btn small primary" data-cmd-send>发送</button>' +
        "</div>" +
      "</div>"
    );
  }

  function stateChipsHtml(st) {
    if (!st) return "";
    var chips = [];
    for (var k in st) {
      var v = st[k];
      if (k === "power") {
        var on = v === "on" || v === true;
        chips.push('<span class="state-chip ' + (on ? "on" : "off") + '">' + (on ? "● 开" : "○ 关") + "</span>");
      } else {
        chips.push('<span class="state-chip">' + esc(k) + ": " + esc(v) + "</span>");
      }
    }
    return chips.join("");
  }

  function deviceControls(d) {
    var actions = d.actions || [];
    var st = d.state || {};
    var html = "";

    // 电源开关
    var hasPower = actions.indexOf("turn_on") >= 0 || actions.indexOf("turn_off") >= 0;
    if (hasPower) {
      var on = st.power === "on" || st.power === true;
      html += '<button class="power-btn ' + (on ? "on" : "") + '" data-action="' + (on ? "turn_off" : "turn_on") + '" title="开关"></button>';
    }

    // 亮度滑条
    if (actions.indexOf("set_brightness") >= 0) {
      var b = st.brightness != null ? st.brightness : 50;
      html += '<span class="slider-wrap">亮度 <input type="range" min="1" max="100" value="' + b + '" data-slider="brightness"><span class="val">' + b + "%</span></span>";
    }

    // 色温滑条
    if (actions.indexOf("set_color_temp") >= 0) {
      var ct = st.color_temp != null ? st.color_temp : 4000;
      html += '<span class="slider-wrap">色温 <input type="range" min="2700" max="6500" step="100" value="' + ct + '" data-slider="color_temp"><span class="val">' + ct + "K</span></span>";
    }

    // 温度步进器
    if (actions.indexOf("set_temperature") >= 0) {
      var temp = st.temperature != null ? st.temperature : 26;
      html += '<span class="stepper">温度 <button class="btn small" data-step="temperature" data-delta="-1">−</button><span class="val">' + temp + "℃</span><button class=\"btn small\" data-step=\"temperature\" data-delta=\"1\">＋</button></span>";
    }

    // 风扇档位
    if (actions.indexOf("set_fan_speed") >= 0) {
      var fs = st.fan_speed != null ? st.fan_speed : 3;
      html += '<span class="stepper">风速 <button class="btn small" data-step="fan_speed" data-delta="-1">−</button><span class="val">' + fs + "</span><button class=\"btn small\" data-step=\"fan_speed\" data-delta=\"1\">＋</button></span>";
    }

    // 其他通用动作（排除已处理的）
    var handled = ["turn_on", "turn_off", "set_brightness", "set_color_temp", "set_temperature", "set_fan_speed"];
    actions.forEach(function (a) {
      if (handled.indexOf(a) >= 0) return;
      if (a === "get_state") return;
      html += '<button class="btn small" data-action="' + esc(a) + '">' + esc(a) + "</button>";
    });

    return html;
  }

  function bindDeviceEvents() {
    // 开关按钮
    $all(".power-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var card = btn.closest(".device-card");
        controlDevice(card.dataset.id, btn.dataset.action, {});
      });
    });

    // 通用动作按钮
    $all(".device-actions [data-action]").forEach(function (btn) {
      if (btn.classList.contains("power-btn")) return;
      btn.addEventListener("click", function () {
        var card = btn.closest(".device-card");
        controlDevice(card.dataset.id, btn.dataset.action, {});
      });
    });

    // 滑条
    $all("input[data-slider]").forEach(function (sl) {
      var key = sl.dataset.slider;
      sl.addEventListener("input", function () {
        var card = sl.closest(".device-card");
        var wrap = sl.closest(".slider-wrap");
        wrap.querySelector(".val").textContent = key === "color_temp" ? sl.value + "K" : sl.value + "%";
      });
      sl.addEventListener("change", function () {
        var card = sl.closest(".device-card");
        controlDevice(card.dataset.id, "set_" + key, (_ = {}, _[key] = parseInt(sl.value, 10), _));
      });
    });

    // 步进器
    $all("[data-step]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var card = btn.closest(".device-card");
        var key = btn.dataset.step;
        var delta = parseInt(btn.dataset.delta, 10);
        var valEl = btn.closest(".stepper").querySelector(".val");
        var cur = parseInt(valEl.textContent, 10) || 0;
        var next = cur + delta;
        var params = {};
        params[key] = next;
        controlDevice(card.dataset.id, "set_" + key, params);
      });
    });

    // 自然语言命令
    $all(".device-card").forEach(function (card) {
      var input = card.querySelector("[data-cmd-input]");
      var send = card.querySelector("[data-cmd-send]");
      function go() {
        var text = input.value.trim();
        if (!text) return;
        controlByText(card.dataset.id, text);
        input.value = "";
      }
      send.addEventListener("click", go);
      input.addEventListener("keydown", function (e) { if (e.key === "Enter") go(); });
    });
  }

  function controlDevice(id, action, params) {
    api("/api/devices/" + id + "/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action, params: params }),
    }).then(function (j) {
      if (j.ok) {
        showToast((j.data.action || "执行") + " 完成", "success");
        fetchState();
      } else {
        showToast(j.error, "error");
        fetchState();
      }
    });
  }

  function controlByText(id, text) {
    api("/api/devices/" + id + "/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
    }).then(function (j) {
      if (j.ok) {
        showToast("已理解并执行", "success");
        fetchState();
      } else {
        showToast(j.error, "error");
        fetchState();
      }
    });
  }

  // ---------- 添加设备 ----------
  function renderSamples() {
    var box = $("#samples");
    box.innerHTML = Object.keys(SAMPLES).map(function (name) {
      return '<button class="btn small" data-sample="' + esc(name) + '">' + esc(name) + "</button>";
    }).join("");
    $all("[data-sample]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        $("#manual").value = SAMPLES[btn.dataset.sample];
        $("#name-hint").value = btn.dataset.sample;
        showToast("已填入示例说明书");
      });
    });
  }

  function bindAddDevice() {
    $("#btn-add").addEventListener("click", function () {
      var manual = $("#manual").value.trim();
      var deviceId = $("#device-id").value.trim();
      var nameHint = $("#name-hint").value.trim();
      var result = $("#add-result");

      if (!manual) { showToast("请先粘贴说明书内容", "error"); return; }

      $("#btn-add").disabled = true;
      result.className = "add-result";
      result.textContent = "正在编译说明书…（需要 LLM，首次可能较慢）";

      api("/api/devices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manual: manual, device_id: deviceId, name_hint: nameHint }),
      }).then(function (j) {
        $("#btn-add").disabled = false;
        if (j.ok) {
          result.className = "add-result ok";
          result.textContent = "✅ " + j.message + "\n\n" + JSON.stringify(j.data, null, 2);
          showToast(j.message, "success");
          $("#manual").value = "";
          $("#device-id").value = "";
          fetchState();
        } else {
          result.className = "add-result err";
          result.textContent = "❌ " + j.error;
          showToast(j.error, "error");
        }
      });
    });
  }

  // ---------- 场景 ----------
  function renderScenes() {
    var grid = $("#scenes-grid");
    if (!state.scenes.length) {
      grid.innerHTML = '<div class="empty">暂无场景</div>';
      return;
    }
    grid.innerHTML = state.scenes.map(function (s) {
      var steps = s.steps.map(function (st) {
        return '<span class="scene-step">' + esc(st.device_id) + " · " + esc(st.action) + "</span>";
      }).join("");
      return (
        '<div class="scene-card">' +
          '<div class="scene-name">🏠 ' + esc(s.name) + "</div>" +
          '<div class="scene-desc">' + esc(s.description || "") + "</div>" +
          '<div class="scene-steps">' + steps + "</div>" +
          '<button class="btn primary" data-scene="' + esc(s.name) + '">触发</button>' +
        "</div>"
      );
    }).join("");

    $all("[data-scene]").forEach(function (btn) {
      btn.addEventListener("click", function () { triggerScene(btn.dataset.scene); });
    });
  }

  function triggerScene(name) {
    api("/api/scenes/" + encodeURIComponent(name) + "/trigger", { method: "POST" }).then(function (j) {
      if (j.ok) {
        var done = j.data.filter(function (r) { return !r.error; }).length;
        showToast("场景「" + name + "」已触发，" + done + " 个动作完成", "success");
        fetchState();
      } else {
        showToast(j.error, "error");
      }
    });
  }

  // ---------- 自动化 ----------
  function renderAutomations() {
    var list = $("#automations-list");
    if (!state.automations.length) {
      list.innerHTML = '<div class="empty">暂无自动化规则</div>';
      return;
    }
    list.innerHTML = state.automations.map(function (r) {
      var actions = (r.actions || []).map(function (a) {
        return a.device_id + "." + a.action;
      }).join(", ");
      return (
        '<div class="automation-card">' +
          '<div class="automation-icon">⚙️</div>' +
          '<div class="automation-body">' +
            '<div class="automation-name">' + esc(r.name) + "</div>" +
            '<div class="automation-trigger">当 ' + esc(r.trigger) + "</div>" +
            '<div class="automation-desc">' + esc(r.description || "") + ' → ' + esc(actions) + "</div>" +
          "</div>" +
        "</div>"
      );
    }).join("");
  }

  function bindAutomation() {
    $all("[data-sim]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var ctx = JSON.parse(btn.dataset.sim);
        api("/api/automation/tick", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(ctx),
        }).then(function (j) {
          if (j.ok) {
            var fired = j.data;
            if (fired.length) {
              fired.forEach(function (r) {
                showToast("触发「" + r.rule + "」", "success");
              });
            } else {
              showToast("环境变化已接收，无规则触发");
            }
            fetchState();
          } else {
            showToast(j.error, "error");
          }
        });
      });
    });

    $("#btn-reset").addEventListener("click", function () {
      api("/api/automation/reset", { method: "POST" }).then(function () {
        showToast("触发状态已重置");
      });
    });
  }

  // ---------- 联动 ----------
  function renderLinkages() {
    var list = $("#linkages-list");
    if (!state.linkages.length) {
      list.innerHTML = '<div class="empty">暂无联动。接入新传感器设备后，会自动发现与现有设备的联动关系</div>';
      return;
    }
    list.innerHTML = state.linkages.map(function (l) {
      return (
        '<div class="linkage-card">' +
          '<div class="linkage-icon">🔗</div>' +
          '<div class="linkage-text">新设备 <strong>' + esc(l.device) + "</strong> 自动生成规则：<strong>" + esc(l.rule) + "</strong></div>" +
        "</div>"
      );
    }).join("");
  }

  // ---------- Tab 切换 ----------
  function bindTabs() {
    $all(".tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        $all(".tab").forEach(function (t) { t.classList.remove("active"); });
        $all(".tab-panel").forEach(function (p) { p.classList.remove("active"); });
        tab.classList.add("active");
        $("#tab-" + tab.dataset.tab).classList.add("active");
      });
    });
  }

  // ---------- 启动 ----------
  function init() {
    bindTabs();
    renderSamples();
    bindAddDevice();
    bindAutomation();
    fetchState();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
