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
                const temp = item.status.startsWith("TEM") ? "(未成交)" : "";
                const tempPrice = item.status.startsWith("TEM") ? "(预估)" : "";
                today += `<div><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a></div><div>${TradeStatus[item.status] + temp}</div><div>${item.price}${tempPrice}</div><div>${item.shares}</div><div>分析</div></div>`;
            });
            data.data.holdList.forEach(item => {
                hold += `<div><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a></div><div>${item.create_time}</div><div>${item.price}</div><div>${item.shares}</div><div>${(item.price * item.shares + item.profit).toFixed(2)}</div><div>${item.profit}</div></div>`;
            });
            let figure = document.getElementById("capital-figure");
            figure.style.width = parseInt(document.body.clientWidth * 0.5) + 'px';
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

getTradeData();
