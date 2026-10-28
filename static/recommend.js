const pageSize = 20;
const defaultUserId = "99";
const TradeStatus = {"RECD": "买入", "AIS": "卖出", "TEMB": "买入", "TEMS": "卖出"}
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
                today += `<div><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a></div><div>${TradeStatus[item.status] + temp}</div><div>${item.price}${tempPrice}</div><div>${item.shares}</div><div onclick="show_concept('${item.code}');" style="cursor:pointer;">点我</div><div id="ai-${item.code}" style="display:none;">${item.content}</div></div>`;
            });
            data.data.holdList.forEach(item => {
                hold += `<div><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a></div><div>${item.create_time}</div><div>${item.price}</div><div>${item.shares}</div><div>${(item.price * item.shares + item.profit).toFixed(2)}</div><div>${item.profit}</div></div>`;
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

function show_concept(code) {
    let codeEle = document.getElementById('ai-' + code);
    const data = JSON.parse(codeEle.innerText);
    document.getElementById("stock-info").innerText = `${code} - ${data.name}`;
    document.getElementById("stock-rank").innerText = data.rating;
    document.getElementById("stock-core-text").innerText = data.action_plan.operation_reason.replace('\\n', '\n');
    document.getElementById("stock-detail-text").innerText = data.detailed_analysis.replace('\\n', '\n');
    document.getElementById("stock-risk").innerText = data.risk_warning.replace('\\n', '\n');
    document.getElementById("stock-position").innerText = data.action_plan.stop_loss_profit;
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

getTradeData();
