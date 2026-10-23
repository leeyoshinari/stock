const pageSize = 20;
const defaultUserId = "99";
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

function getStockRegion(code) {
    if (code.startsWith("60") || code.startsWith("68")) {
        return "sh"
    } else {
        return "sz"
    }
}

function getStockList() {
    let filter = document.getElementById("filter-by").value;
    // let region = document.getElementById("stock-region").value;
    let industry = document.getElementById("stock-industry").value;
    let concept = document.getElementById("stock-concept").value;
    let url = prefix + `/stock/list?pageSize=${pageSize}&page=${page}`;
    let stock_name = document.getElementById("stock-name").value;
    let stock_code = document.getElementById("stock-code").value;
    let userId = localStorage.getItem('userId') || defaultUserId;
    if (stock_code && stock_code.trim()) {
        url = url + `&code=${stock_code}`;
    }
    if (stock_name && stock_name.trim()) {
        url = url + `&name=${stock_name}`;
    }
    if (filter && filter.trim()) {
        url = url + `&filter=${filter}`;
    }
    // if (region && region.trim()) {
    //     url = url + `&region=${region}`;
    // }
    if (industry && industry.trim()) {
        url = url + `&industry=${industry}`;
    }
    if (concept && concept.trim()) {
        url = url + `&concept=${concept}`;
    }
    if (userId && userId.trim()) {
        url = url + `&userId=${userId}`;
    }
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = "";
            data.data.forEach(item => {
                let setFlag = ``;
                if (showFlag) {
                    setFlag = `<img id="show-${item.code}" src="${prefix}/static/copy.svg" alt="" onclick="show_stock_filter('${item.code}');" />`;
                }
                s += `<div id="${item.code}" class="item-list"><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a><img id="hold-${item.code}" src="${prefix}/static/copy.svg" alt="" onclick="hold_stock('${item.code}', '${item.name}');" />${setFlag}</div><div><a onclick="get_stock_real_figure('${item.code}');">${item.code}</a><img id="copy-${item.code}" src="${prefix}/static/copy.svg" alt="" /></div>
                      <div><img id="shrink-${item.code}" src="${prefix}/static/shrink.svg" alt="" onclick="analysize_stock_ai('${item.code}', '${item.name}');" style="width:20px;" /></div>
                      <div><a target="_blank" href="https://quote.eastmoney.com/concept/${getStockRegion(item.code)}${item.code}.html#chart-k-cyq">${item.region}</a></div><div>${item.industry}</div><div id="concept-${item.code}" onclick="show_concept('${item.code}');">${item.concept}</div></div>`;
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
    let userId = localStorage.getItem('userId') || defaultUserId;
    fetch(`${prefix}/get?code=${code}&userId=${userId}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let figure = document.getElementById("figure");
                figure.style.width = parseInt(document.body.clientWidth * 0.85) + 'px';
                figure.style.height = '';
                figure.removeAttribute("_echarts_instance_");
                figure.innerHTML = '';
                let profit = '';
                let isEtf = false;
                if (data.data.shares) {
                    profit = ` - 成本: ${data.data.cost}元, 数量: ${data.data.shares}股, 利润: ${data.data.profit}元`;
                }
                let region_str = ` - ${data.data.region}`;
                if (code.startsWith("1") || code.startsWith("5")){
                    region_str = '';
                    isEtf = true;
                    figure.style.height = '520px';
                }
                let title = `${data.data.name} - ${code}${region_str} - ${data.data.industry}${profit}`;
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, isEtf, title, data.data.x, data.data.price, data.data.volume, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.total_shares, data.data.premium, data.data.turnover_rate, data.data.fund, data.data.boll_up, data.data.boll_low, data.data.coord);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
        .finally(() => {close_modal_cover();})
}

function get_stock_real_figure(code) {
    show_modal_cover();
    fetch(`${prefix}/query/day/k?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let region_str = ` - ${data.data.region}`;
                if (code.startsWith("1") || code.startsWith("5")){
                    region_str = '';
                }
                let title = `${data.data.name} - ${code}${region_str} - ${data.data.industry}`;
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

function show_stock_filter(code) {
    let s = `<div class="header">${code}</div><div><div class="title"><label>标签：</label><input type="text" id="filter-values" placeholder="" autocomplete="off"></div><div><button onclick="set_stock_buy('${code}', 'addFilter');">设置</button><button onclick="set_stock_buy('${code}', 'delFilter');">删除</button></div></div>`;
    document.getElementById("data-tips").innerHTML = s;
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

// function buy_stocks(code, name) {
//     let s = `<div class="header">${code} - ${name}</div><div><div class="title"><label>时间：</label><input type="datetime-local" id="buy-time" autocomplete="off"></div><div class="title"><label>价格：</label><input type="text" id="buy-price" placeholder="" autocomplete="off"></div><div class="title"><label>卖出时清仓：</label><select id="sell-empty"><option value='1'>清仓卖出</option><option value='0'>不清仓卖出</option></select></div><div style="margin-top:10px;"><button style="float:right;" onclick="set_stock_buy('${code}', 'setBuy');">买入</button><button onclick="set_stock_buy('${code}', 'setSale');">卖出</button></div></div>`;
//     document.getElementById("data-tips").innerHTML = s;
//     document.getElementsByClassName("stock-data")[0].style.display = "flex";
// }

function hold_stock(code, name) {
    let s = `<div class="header">${code} - ${name}</div><div><div class="title"><label>时间：</label><input type="datetime-local" id="buy-time" autocomplete="off"></div><div class="title"><label>价格：</label><input type="text" id="buy-price" placeholder="" autocomplete="off"></div><div class="title"><label>数量：</label><input type="text" id="buy-number" placeholder="" autocomplete="off"></div><div class="title"><label>用户：</label><select id="hold-user" style="width:99px;height:22px;"><option value='2'>用户1</option><option value='1'>小白</option></select></div><div style="margin-top:10px;"><button style="float:right;" onclick="set_stock_hold('${code}', '1');">买入</button><button onclick="set_stock_hold('${code}', '0');">卖出</button></div></div>`;
    document.getElementById("data-tips").innerHTML = s;
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

function show_concept(code) {
    let codeEle = document.getElementById('concept-' + code);
    document.getElementById("data-tips").innerText = code + '\n' + codeEle.innerText;
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

function analysize_stock_ai(code, name) {
    show_modal_cover();
    let userId = localStorage.getItem('userId') || defaultUserId;
    fetch(`${prefix}/analyzer?code=${code}&userId=${userId}`)
        .then(res => res.json())
        .then(data => {
            if (!data.success) {
                alert(data.msg);
                return;
            }
            document.getElementById("stock-info").innerText = `${code} - ${name}`;
            document.getElementById("stock-rank").innerText = data.data.rating;
            document.getElementById("stock-suggest").innerText = data.data.action_plan.operation;
            document.getElementById("stock-core-text").innerText = data.data.action_plan.operation_reason.replace('\\n', '\n');
            document.getElementById("stock-detail-text").innerText = data.data.detailed_analysis.replace('\\n', '\n');
            document.getElementById("stock-risk").innerText = data.data.risk_warning.replace('\\n', '\n');
            document.getElementById("stock-position").innerText = data.data.action_plan.stop_loss_profit;

            if (data.data.action_plan.operation !== "不操作") {
                document.getElementById("stock-suggest-share").style.display = 'block';
                document.getElementById("stock-suggest-money").style.display = 'block';
                document.getElementById("stock-suggest-share-data").style.display = 'block';
                document.getElementById("stock-suggest-money-data").style.display = 'block';
                document.getElementById("stock-suggest-share-data").innerText = data.data.action_plan.operation_shares;
                document.getElementById("stock-suggest-money-data").innerText = data.data.action_plan.operation_amount;
            } else {
                document.getElementById("stock-suggest-share").style.display = 'none';
                document.getElementById("stock-suggest-money").style.display = 'none';
                document.getElementById("stock-suggest-share-data").style.display = 'none';
                document.getElementById("stock-suggest-money-data").style.display = 'none';
            }
            if (data.data.action_plan.current_position && data.data.action_plan.current_position.shares > 0) {
                document.getElementById("stock-hold").style.display = 'block';
                document.getElementById("stock-hold-data").innerText = `成本: ${data.data.action_plan.current_position.price}, 股数: ${data.data.action_plan.current_position.shares}`;
            } else {
                document.getElementById("stock-hold").style.display = 'none';
            }
            document.getElementsByClassName("stock-analysize")[0].style.display = "flex";
        })
        .finally(() => {close_modal_cover();})
}

function set_stock_buy(code, operate_type) {
    let data = { code, operate_type };
    // if (operate_type === "setBuy" || operate_type === "setSale") {
    //     let buy_time = document.getElementById("buy-time").value;
    //     let buy_price = document.getElementById("buy-price").value;
    //     let sell_empty = document.getElementById("sell-empty").value;
    //     data = { ...data, buy_time, buy_price, sell_empty };
    // }
    // if (operate_type === "addFilter" || operate_type === "delFilter") {
    let tag = document.getElementById("filter-values").value;
    data = { ...data, tag };
    // }
    let headers = {'content-type': 'application/json;charset=UTF-8'};
    fetch(`${prefix}/set/stock`, {
        method: "POST",
        headers: { ...headers },
        body: JSON.stringify(data)
    }).then(res => res.json())
    .then(data => {
        if (!data.success) {alert(data.msg);} else {document.getElementsByClassName("stock-data")[0].style.display = "none";}
    })
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
const overlay_analysize = document.querySelector('.stock-analysize');
overlay.addEventListener('click', function(event) {
  if (event.target === overlay) {overlay.style.display = 'none';}
});
overlay_data.addEventListener('click', function(event) {
  if (event.target === overlay_data) {overlay_data.style.display = 'none';}
});
overlay_analysize.addEventListener('click', function(event) {
  if (event.target === overlay_analysize) {overlay_analysize.style.display = 'none';}
});

document.getElementById("pre-page").disabled = 'true';
getStockList();
watchInput(document.getElementById('stock-name'), getStockList);
watchInput(document.getElementById('stock-code'), getStockList);
// watchInput(document.getElementById('stock-region'), getStockList);
watchInput(document.getElementById('stock-industry'), getStockList);
watchInput(document.getElementById('stock-concept'), getStockList);
