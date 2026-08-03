const pageSize = 20;
let page = 1;
const showFlag = window.location.href.endsWith("trump");
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  const defaultHeaders = {'referered': localStorage.getItem("pwd")};
  const headers = {...defaultHeaders,...(options.headers || {})};
  return originalFetch(url, {...options,headers});
};

function currentDate() {
    const date = new Date();
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function getDayDiff(startDateStr, endDateStr) {
    const start = new Date(startDateStr);
    const end = new Date(endDateStr);
    const diffInMs = end - start;
    const diffInDays = Math.floor(diffInMs / (1000 * 60 * 60 * 24));
    return diffInDays + 1;
}

document.getElementById("pre-page").addEventListener("click", () => {
    page -= 1;
    if (page <= 1) {
        document.getElementById("pre-page").disabled = 'true';
        document.getElementById("next-page").disabled = '';
    }
    getStockList();
})

document.getElementById("next-page").addEventListener("click", () => {
    page += 1;
    if (page > 1) {
        document.getElementById("pre-page").disabled = '';
    }
    getStockList();
})

function getStockList() {
    let url = prefix + `/hold/list?pageSize=20&page=${page}`;
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = "";
            data.data.forEach(item => {
                let sale_time = currentDate();
                if (item.sale_time && item.sale_time.length > 6) {
                    sale_time = item.sale_time;
                }
                let profit = `<div><a onclick="query_profit('${item.id}', '${item.code}')" style="cursor:pointer;">查看</a></div>`;
                let profit_color = '';
                if (item.sale_price && item.sale_price > 0 && item.shares === 0) {
                    profit = ((item.sale_price - item.price) / item.price * 100).toFixed(2) + '%';
                    profit_color = item.sale_price > item.price ? "red" : item.sale_price < item.price ? "green" : "";
                }
                let deleteR = '';
                if (showFlag) {
                    deleteR = `<div><a onclick="delete_data('${item.id}')">删除</a></div>`;
                }
                s += `<div id="${item.code}-${item.create_time}" class="item-list"><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a></div>
                      <div id="price-${item.id}">${item.price}</div><div>${item.shares > 0 ? item.shares : "已清仓"}</div><div>${item.create_time}</div><div>${getDayDiff(item.create_time, sale_time)}</div><div id="profit-${item.id}" style="color:${profit_color};">${profit}</div>${deleteR}</div>`;
            })
            document.getElementsByClassName("list")[0].innerHTML = s;
            if (page === parseInt((data.total + pageSize -1) / pageSize)) {
                document.getElementById("next-page").disabled = 'true';
            }
        })
}

function get_stock_figure(code) {
    show_modal_cover();
    let site = localStorage.getItem('site');
    fetch(`${prefix}/get?code=${code}&site=${site}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.width = parseInt(document.body.clientWidth * 0.85) + 'px';
                figure.style.height = '';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, title, data.data.x, data.data.price, data.data.volume, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.trix, data.data.trma, data.data.turnover_rate, data.data.fund, data.data.boll_up, data.data.boll_low, data.data.coord);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
        .finally(() => {close_modal_cover();})
}

function get_stock_real_figure(code) {
    show_modal_cover();
    let site = localStorage.getItem('site');
    fetch(`${prefix}/query/day/k?code=${code}&site=${site}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.width = parseInt(document.body.clientWidth * 0.85) + 'px';
                figure.style.height = '500px';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_minute_line(stockChart, title, data.data.x, data.data.price, data.data.price_avg, data.data.volume);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
        .finally(() => {close_modal_cover();})
}

function query_profit(itemId, code) {
    show_modal_cover();
    fetch(`${prefix}/query/price?code=${code}&site=`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let current_price = data.data;
                let buy_price = parseFloat(document.getElementById(`price-${itemId}`).innerText);
                let ele = document.getElementById(`profit-${itemId}`);
                ele.style.color = current_price > buy_price ? "red" : current_price < buy_price ? "green" : "";
                ele.innerText = ((current_price - buy_price) / buy_price * 100).toFixed(2) + '%';
            }
        })
        .finally(() => {close_modal_cover();})
}

function delete_data(codeId) {
    fetch(`${prefix}/deleteHold?hId=${codeId}`)
        .then(res => res.json())
        .then(data => {getStockList();})
}

function show_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'flex';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'flex';}
function close_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'none';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'none';}

const overlay = document.querySelector('.stock-chart');
const overlay_data = document.querySelector('.stock-data');
overlay.addEventListener('click', function(event) {
  if (event.target === overlay) {overlay.style.display = 'none';}
});
overlay_data.addEventListener('click', function(event) {
  if (event.target === overlay_data) {overlay_data.style.display = 'none';}
});

document.getElementById("pre-page").disabled = 'true';
getStockList();
