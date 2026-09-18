const pageSize = 20;
const showFlag = window.location.href.endsWith("trump");
let page = 1;
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  const defaultHeaders = {'referered': localStorage.getItem("pwd")};
  const headers = {...defaultHeaders,...(options.headers || {})};
  return originalFetch(url, {...options,headers});
};
function watchInput(el, callback, delay = 500) {
  let timer = null, composing = false;
  const fire = e => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      callback({
        value: el.value ?? el.innerText,
        type: e.inputType || e.type
      });
    }, delay);
  };
  el.addEventListener('compositionstart', () => composing = true);
  el.addEventListener('compositionend', e => { composing = false; fire(e); });
  el.addEventListener('input', e => { if (!composing) fire(e); });
}
// document.addEventListener('keypress', function(event) {
//     if (event.key === 'Enter') {
//         page = 1; getStockList();
//     }
// });

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
    let filter = document.getElementById("filter-by").value;
    let url = prefix + `/etf/list?pageSize=${pageSize}&page=${page}`;
    let stock_name = document.getElementById("stock-name").value;
    let stock_code = document.getElementById("stock-code").value;
    if (stock_code || stock_code.trim()) {
        url = url + `&code=${stock_code}`;
    }
    if (stock_name || stock_name.trim()) {
        url = url + `&name=${stock_name}`;
    }
    if (filter || filter.trim()) {
        url = url + `&sortField=${filter}`;
    }
    if (showFlag) {
        url = url + `&filter=0`;
    }
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = "";
            data.data.forEach(item => {
                let setFlag = ``;
                if (showFlag) {
                    setFlag = `<div><a onclick="set_etf('${item.code}', ${item.running === 1 ? 0 : 1});" style="margin-right:3%;">${item.running === 1 ? 'No' : 'Yes'}</a><a onclick="delete_etf('${item.code}');">删除</a></div>`;
                }
                s += `<div id="${item.code}" class="item-list"><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a><img id="hold-${item.code}" src="${prefix}/static/copy.svg" alt="" onclick="hold_stock('${item.code}', '${item.name}');" /></div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a><img id="copy-${item.code}" src="${prefix}/static/copy.svg" alt="" /></div>
                      <div>${item.capital}</div><div>${item.fee}%</div><div>${item.create_time}</div><div>${item.industry}</div>${setFlag}</div>`;
            })
            document.getElementsByClassName("list")[0].innerHTML = s;
            if (page === parseInt((data.total + pageSize -1) / pageSize)) {
                document.getElementById("next-page").disabled = 'true';
            }
            document.querySelectorAll('[id*="copy-"]').forEach( item => {
                item.addEventListener('click', (event) => {
                    if (navigator.clipboard && window.isSecureContext) {
                        navigator.clipboard.writeText(event.target.id.split('-')[1]);
                    }
                })
            })
        })
}

function change_select() {page = 1;getStockList();}

function get_stock_figure(code) {
    show_modal_cover();
    let site = localStorage.getItem('site');
    fetch(`${prefix}/get?code=${code}&site=${site}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.industry}`;
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
                let title = `${data.data.name} - ${code} - ${data.data.industry}`;
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

function sell_stock_ai(code, name) {
    document.getElementsByClassName("stock-data")[0].style.display = "none";
    let buy_time = document.getElementById("buy-time").value;
    let buy_price = document.getElementById("buy-price").value;
    let site = localStorage.getItem('site');
    show_modal_cover();
    fetch(`${prefix}/sell/stock?code=${code}&price=${buy_price}&t=${buy_time}&site=${site}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("data-tips").innerText = `${code} - ${name} : ` + data.data;
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
        .finally(() => {close_modal_cover();})
}

function delete_etf(code) {
    show_modal_cover();
    fetch(`${prefix}/etf/delete?code=${code}`)
        .then(res => res.json())
        .then(data => {getStockList();})
        .finally(() => {close_modal_cover();})
}

function set_etf(code, running) {
    show_modal_cover();
    fetch(`${prefix}/etf/set?code=${code}&running=${running}`)
        .then(res => res.json())
        .then(data => {getStockList();})
        .finally(() => {close_modal_cover();})
}

function query_stock_ai(code, name, source) {
    show_modal_cover();
    let site = localStorage.getItem('site');
    fetch(`${prefix}/buy/stock?code=${code}&site=${site}&source=${source}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("data-tips").innerText = `${code} - ${name} : ` + data.data;
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
        .finally(() => {close_modal_cover();})
}

function hold_stock(code, name) {
    let s = `<div class="header">${code} - ${name}</div><div><div class="title"><label>时间：</label><input type="datetime-local" id="buy-time" autocomplete="off"></div><div class="title"><label>价格：</label><input type="text" id="buy-price" placeholder="" autocomplete="off"></div><div class="title"><label>数量：</label><input type="text" id="buy-number" placeholder="" autocomplete="off"></div><div class="title"><label>用户：</label><select id="hold-user"><option value='1'>用户1</option><option value='2'>用户2</option></select></div><div style="margin-top:10px;"><button style="float:right;" onclick="set_stock_hold('${code}', '1');">买入</button><button onclick="set_stock_hold('${code}', '0');">卖出</button></div></div>`;
    document.getElementById("data-tips").innerHTML = s;
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

function set_stock_hold(code, status) {
    let time = document.getElementById("buy-time").value;
    let price = document.getElementById("buy-price").value;
    let number = document.getElementById("buy-number").value;
    let userId = document.getElementById("hold-user").value;
    let data = { code, status, time, price, number, userId };

    let headers = {'content-type': 'application/json;charset=UTF-8'};
    fetch(`${prefix}/hold/set`, {
        method: "POST",
        headers: { ...headers },
        body: JSON.stringify(data)
    }).then(res => res.json())
    .then(data => {
        if (!data.success) {alert(data.msg);} else {document.getElementsByClassName("stock-data")[0].style.display = "none";}
    })
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
watchInput(document.getElementById('stock-name'), getStockList);
watchInput(document.getElementById('stock-code'), getStockList);
