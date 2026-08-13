// DeviceMind Web UI —— 设备说明书编译器（方向 A：HA 设备接入增强层）
(function () {
  "use strict";

  // 示例说明书（一键体验）
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

  function getToken() {
    try { return localStorage.getItem("devicemind_token") || ""; }
    catch (e) { return ""; }
  }

  function promptToken() {
    var token = window.prompt("此实例启用了 API Token 鉴权，请输入 Token：");
    if (token) {
      try { localStorage.setItem("devicemind_token", token.trim()); } catch (e) {}
      refresh();
    }
  }

  function api(path, opts) {
    opts = opts || {};
    opts.headers = opts.headers || {};
    var token = getToken();
    if (token) {
      opts.headers["X-API-Token"] = token;
    }
    return fetch(path, opts).then(function (r) {
      if (r.status === 401) {
        promptToken();
        return Promise.reject(new Error("未授权"));
      }
      return r.json();
    });
  }

  // ---------- 状态 ----------
  function setStatus(ok) {
    $("#status-dot").className = "dot" + (ok ? "" : " off");
    $("#status-text").textContent = ok ? "已连接" : "连接失败";
  }

  function refresh() {
    api("/api/devices").then(function (j) {
      if (j.ok) {
        setStatus(true);
        renderDevices(j.data);
      } else {
        setStatus(false);
      }
    }).catch(function () { setStatus(false); });
  }

  // ---------- 编译 ----------
  var lastPreview = null;  // 最近一次编译预览结果

  function bindCompile() {
    $("#btn-compile").addEventListener("click", function () {
      var manual = $("#manual").value.trim();
      var deviceId = $("#device-id").value.trim();
      var nameHint = $("#name-hint").value.trim();
      var result = $("#compile-result");

      if (!manual) { showToast("请先粘贴说明书内容", "error"); return; }

      $("#btn-compile").disabled = true;
      result.className = "add-result";
      result.textContent = "正在编译说明书…（需要 LLM，首次可能较慢）";

      api("/api/compile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manual: manual, device_id: deviceId, name_hint: nameHint }),
      }).then(function (j) {
        $("#btn-compile").disabled = false;
        if (j.ok) {
          lastPreview = { manual: manual, device_id: j.data.id, name_hint: nameHint };
          result.className = "add-result ok";
          result.innerHTML = '<pre>' + esc(JSON.stringify(j.data, null, 2)) + '</pre>';
          $("#btn-save").disabled = false;
          showToast("编译完成，可保存或直接复制 JSON", "success");
        } else {
          lastPreview = null;
          result.className = "add-result err";
          result.textContent = "❌ " + j.error;
          $("#btn-save").disabled = true;
          showToast(j.error, "error");
        }
      });
    });

    $("#btn-save").addEventListener("click", function () {
      if (!lastPreview) return;
      api("/api/devices", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(lastPreview),
      }).then(function (j) {
        if (j.ok) {
          showToast(j.message, "success");
          $("#btn-save").disabled = true;
          $("#manual").value = "";
          $("#device-id").value = "";
          refresh();
        } else {
          showToast(j.error, "error");
        }
      });
    });
  }

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

  // ---------- 已编译设备列表 ----------
  function renderDevices(devices) {
    var list = $("#devices-list");
    if (!devices.length) {
      list.innerHTML = '<div class="empty">还没有编译过的设备，去「编译设备」接入第一个吧</div>';
      return;
    }
    list.innerHTML = devices.map(function (d) {
      return (
        '<div class="device-card" data-id="' + esc(d.id) + '">' +
          '<div class="device-head">' +
            '<div class="device-head-main">' +
              '<div class="device-name">' + esc(d.name) + "</div>" +
              '<div class="device-id">' + esc(d.id) + " · " + esc(d.type) + "</div>" +
            "</div>" +
            '<button class="btn small" data-json="' + esc(d.id) + '">查看 JSON</button>' +
            '<button class="btn small ghost" data-del="' + esc(d.id) + '">删除</button>' +
          "</div>" +
          '<pre class="device-json hidden" id="json-' + esc(d.id) + '"></pre>' +
        "</div>"
      );
    }).join("");

    $all("[data-json]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.dataset.json;
        var pre = $("#json-" + id);
        api("/api/devices/" + id).then(function (j) {
          if (j.ok) {
            pre.textContent = JSON.stringify(j.data, null, 2);
            pre.classList.toggle("hidden");
          } else {
            showToast(j.error, "error");
          }
        });
      });
    });

    $all("[data-del]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var id = btn.dataset.del;
        if (!window.confirm("确定删除该设备的编译缓存吗？")) return;
        api("/api/devices/" + id, { method: "DELETE" }).then(function (j) {
          showToast(j.ok ? j.message : j.error, j.ok ? "success" : "error");
          refresh();
        });
      });
    });
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
    bindCompile();
    refresh();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
