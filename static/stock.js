const pageSize = 20;
let page = 1;
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  const defaultHeaders = {'referered': localStorage.getItem("pwd")};
  const headers = {...defaultHeaders,...(options.headers || {})};
  return originalFetch(url, {...options,headers});
};
document.getElementById("search").addEventListener("click", () => {
    page = 1; getStockList();
})
document.addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {
        page = 1; getStockList();
    }
});

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
    let region = document.getElementById("stock-region").value;
    let industry = document.getElementById("stock-industry").value;
    let concept = document.getElementById("stock-concept").value;
    let url = prefix + `/stock/list?pageSize=20&page=${page}`;
    let stock_name = document.getElementById("stock-name").value;
    let stock_code = document.getElementById("stock-code").value;
    if (stock_code || stock_code.trim()) {
        url = url + `&code=${stock_code}`;
    }
    if (stock_name || stock_name.trim()) {
        url = url + `&name=${stock_name}`;
    }
    if (filter || filter.trim()) {
        url = url + `&filter=${filter}`;
    }
    if (region || region.trim()) {
        url = url + `&region=${region}`;
    }
    if (industry || industry.trim()) {
        url = url + `&industry=${industry}`;
    }
    if (concept || concept.trim()) {
        url = url + `&concept=${concept}`;
    }
    let showFlag = window.location.href.endsWith("trump");
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = "";
            data.data.forEach(item => {
                let myself = ``;
                if (item.filter.indexOf("myself") > -1) {
                    myself = `<img onclick="click_stock_code('${item.code}');" id="trend-${item.code}" src="${prefix}/static/trend.svg" alt="" />`;
                }
                let setFlag = ``;
                if (showFlag) {
                    setFlag = `<img id="show-${item.code}" src="${prefix}/static/copy.svg" alt="" onclick="show_stock_filter('${item.code}');" />`;
                }
                s += `<div id="${item.code}" class="item-list"><div><a onclick="get_stock_figure('${item.code}');">${item.name}</a>${setFlag}${myself}</div><div><a target="_blank" href="https://quote.eastmoney.com/concept/${getStockRegion(item.code) + item.code}.html#chart-k-cyq">${item.code}</a><img id="copy-${item.code}" src="${prefix}/static/copy.svg" alt="" /></div>
                      <div><img id="ai-${item.code}" src="${prefix}/static/buy.svg" alt="" onclick="query_stock_ai('${item.code}', '${item.name}');" style="width:20px;margin-right:8%;" /><img id="ai-${item.code}" src="${prefix}/static/sell.svg" alt="" onclick="show_sell_stock_window('${item.code}', '${item.name}');" style="width:20px;" /></div>
                      <div>${item.region}</div><div>${item.industry}</div><div id="concept-${item.code}" onclick="show_concept('${item.code}');">${item.concept}</div></div>`;
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
    fetch(prefix + `/get?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.style.width = parseInt(document.body.clientWidth * 0.8) + 'px';
                figure.style.height = '';
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, title, data.data.x, data.data.price, data.data.volumn, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.trix, data.data.trma, data.data.turnover_rate, data.data.fund, data.data.boll_up, data.data.boll_low);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

function click_stock_code(code) {
    fetch(prefix + `/query/recommend/real?code=${code}`)
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
            let figure = document.getElementById("figure");
            figure.style.height = '500px';
            figure.removeAttribute("_echarts_instance_")
            figure.innerHTML = '';
            let stockChart = echarts.init(figure);
            plot_minute_line(stockChart, title, data.data.x, data.data.price, data.data.volume);
            document.getElementsByClassName("stock-chart")[0].style.display = "flex";
        }
    })
}

function show_stock_filter(code) {
    let s = `<div class="header">${code}</div><div><div class="title"><label>标签：</label><input type="text" id="filter-values" placeholder="" autocomplete="off"></div><div><button onclick="set_stock_filter('${code}', 1);">设置</button><button onclick="set_stock_filter('${code}', 0);">删除</button></div></div>`;
    document.getElementById("data-tips").innerHTML = s;
    document.getElementById("data-tips").style.width = "auto";
    document.getElementById("data-tips").style.transform = 'translate(100%,0%)';
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

function show_concept(code) {
    let codeEle = document.getElementById('concept-' + code);
    document.getElementById("data-tips").innerText = code + '\n' + codeEle.innerText;
    document.getElementById("data-tips").style.width = '70%';
    document.getElementById("data-tips").style.transform = 'translate(15%,0%)';
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

function set_stock_filter(code, value) {
    let filter = document.getElementById("filter-values").value;
    fetch(prefix + `/stock/setFilter?code=${code}&filter=${filter}&operate=${value}`)
        .then(res => res.json())
        .then(data => {
            if (!data.success) {alert(data.msg);}
        })
}

function show_sell_stock_window(code, name) {
    let s = `<div class="header">${code} - ${name}</div><div><div class="title"><label>买入时间：</label><input type="text" id="buy-time" placeholder="20260521" autocomplete="off"></div><div class="title"><label>买入成本：</label><input type="text" id="buy-price" placeholder="" autocomplete="off"></div><div style="margin-top:10px;"><button style="float:right;" onclick="sell_stock_ai('${code}', '${name}');">确定</button></div></div>`;
    document.getElementById("data-tips").innerHTML = s;
    document.getElementById("data-tips").style.width = "auto";
    document.getElementById("data-tips").style.transform = 'translate(100%,0%)';
    document.getElementsByClassName("stock-data")[0].style.display = "flex";
}

function sell_stock_ai(code, name) {
    document.getElementsByClassName("stock-data")[0].style.display = "none";
    let buy_time = document.getElementById("buy-time").value;
    let buy_price = document.getElementById("buy-price").value;
    show_modal_cover();
    fetch(prefix + `/sell/stock?code=${code}&price=${buy_price}&t=${buy_time}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("data-tips").innerText = `${code} - ${name} : ` + data.data;
            document.getElementById("data-tips").style.width = '70%';
            document.getElementById("data-tips").style.transform = 'translate(15%,0%)';
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
        .finally(() => {close_modal_cover();})
}

function query_stock_ai(code, name) {
    show_modal_cover();
    fetch(prefix + `/query/ai?code=${code}`)
        .then(res => res.json())
        .then(data => {
            document.getElementById("data-tips").innerText = `${code} - ${name} : ` + data.data;
            document.getElementById("data-tips").style.width = '70%';
            document.getElementById("data-tips").style.transform = 'translate(15%,0%)';
            document.getElementsByClassName("stock-data")[0].style.display = "flex";
        })
        .finally(() => {close_modal_cover();})
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
