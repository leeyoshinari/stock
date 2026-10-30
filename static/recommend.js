const pageSize = 20;
const defaultUserId = "99";
const TradeStatus = {"RECD": "买入", "AIS": "卖出", "TEMB": "买入", "TEMS": "卖出", "FAIL": "买入(未成交)"}
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  const defaultHeaders = {'referered': localStorage.getItem("pwd")};
  const headers = {...defaultHeaders,...(options.headers || {})};
  return originalFetch(url, {...options,headers});
};

function getStockRegion(code) {
    if (code.startsWith("60") || code.startsWith("68")) {
        return "sh"
    } else {
        return "sz"
    }
}

function getTradeData() {
    show_modal_cover();
    fetch(`${prefix}/trade/data`)
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                alert(data.msg);
                return;
            }
            let today = '<div style="font-weight:bold;background-color:inherit !important;"><div>名称</div><div>代码</div><div>交易方向</div><div>价格</div><div>股数</div><div>分析</div></div>';
            let hold = '<div style="font-weight:bold;background-color:inherit !important;"><div>名称</div><div>代码</div><div>建仓时间</div><div>成本</div><div>股数</div><div>持仓金额</div><div>盈利</div></div>';
            data.data.todayList.forEach(item => {
                const temp = item.status.startsWith("TEM") ? "(待成交)" : "";
                const tempPrice = item.status.startsWith("TEM") ? "(预估)" : "";
                today += `<div><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a></div><div>${TradeStatus[item.status] + temp}</div><div>${item.price}${tempPrice}</div><div>${item.shares}</div><div><a onclick="show_concept('${item.code}', '${item.name}');">点我</a></div></div>`;
            });
            data.data.holdList.forEach(item => {
                hold += `<div><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a></div><div><a onclick="show_concept('${item.code}', '${item.name}');">${item.create_time}</a></div><div>${item.price}</div><div>${item.shares}</div><div>${(item.price * item.shares + item.profit).toFixed(2)}</div><div>${item.profit}</div></div>`;
            });
            document.getElementById("curr-day").innerText = data.data.currentDay;
            document.getElementById("curr-total").innerText = data.data.total;
            document.getElementById("curr-av").innerText = data.data.available;
            document.getElementById("curr-hold").innerText = data.data.hold;
            document.getElementById("curr-profit").innerText = data.data.profit + '%';
            let figure = document.getElementById("capital-figure");
            figure.style.width = findMin(document.body.clientWidth, 820) + 'px';
            figure.style.height = '350px';
            figure.removeAttribute("_echarts_instance_")
            figure.innerHTML = '';
            let stockChart = echarts.init(figure);
            plot_trend(stockChart, data.data.day, data.data.ratio, data.data.hs);
            document.getElementById("today-list").innerHTML = today;
            document.getElementById("hold-list").innerHTML = hold;
        })
        .finally(() => {close_modal_cover();})
}

function show_concept(code, name) {
    show_modal_cover();
    // let day = '';
    // if (!flag) {
    //     day = document.getElementById("curr-day").innerText;
    // }
    fetch(`${prefix}/getAnalysis?code=${code}&day=`)
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                alert(data.msg);
                return;
            }
            let s = `<div id="stock-info" style="font-size:larger;font-weight:bold;">${code} - ${name}</div>`;
            data.data.forEach(item => {
                const d = JSON.parse(item.content);
                s += `<hr style="width:100%;"><div style="display:block;"><span style="font-weight:bold;">${item.day} 评级: </span><span id="stock-rank" style="color:red;">${d.rating}</span></div>
                <div style="display:block;"><span style="font-weight:bold;">核心观点: </span><span id="stock-core-text">${d.action_plan.operation_reason.replace('\\n', '\n')}</span></div>
                <div style="display:block;"><span style="font-weight:bold;">详细分析: </span><span id="stock-detail-text">${d.detailed_analysis.replace('\\n', '\n')}</span></div>
                <div style="display:block;"><span style="font-weight:bold;">风险点: </span><span id="stock-risk">${d.risk_warning.replace('\\n', '\n')}</span></div>
                <div style="display:block;"><span style="font-weight:bold;">点位: </span><span id="stock-position">${d.action_plan.stop_loss_profit}</span></div>`;
            })
            document.getElementById("data-tips").innerHTML = s;
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
        .finally(() => {close_modal_cover();})
}

getTradeData();
