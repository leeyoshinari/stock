const pageSize = 20;
let page = 1;
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
  const defaultHeaders = {'referered': localStorage.getItem("pwd")};
  const headers = {...defaultHeaders,...(options.headers || {})};
  return originalFetch(url, {...options,headers});
};

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
    if (page > 1) {document.getElementById("pre-page").disabled = '';}
    getStockList();
})

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

function getStockList() {
    let sortField = document.getElementById("order-by").value;
    let url = prefix + `/list?pageSize=20&page=${page}&sortField=${sortField}`;
    let stock_name = document.getElementById("stock-name").value;
    let stock_code = document.getElementById("stock-code").value;
    if (stock_code || stock_code.trim()) {
        url = url + `&code=${stock_code}`;
    }
    if (stock_name || stock_name.trim()) {
        url = url + `&name=${stock_name}`;
    }
    fetch(url)
        .then(res => res.json())
        .then(data => {
            let s = ""
            data.data.forEach(item => {
                let zhang = (item.current_price - item.last_price) / item.last_price * 100;
                let zhen = (item.max_price - item.min_price) / item.last_price * 100;
                let color = zhang >= 0 ? zhang > 0 ? 'red' : 'black' : 'green';
                s += `<div id="${item.code}" class="item-list" style="color:${color};"><div><a style="cursor:pointer;" onclick="get_stock_figure('${item.code}');">${item.name}</a></div><div><a style="cursor:pointer;" onclick="query_stock_ai('${item.code}', '${item.name}');">${item.code}</a><img id="copy-${item.code}" src="${prefix}/static/copy.svg" alt="" /></div><div>${item.current_price}</div><div>${zhang.toFixed(2)}%</div><div>${zhen.toFixed(2)}%</div>
                      <div>${item.volumn}</div><div>${item.qrr}</div><div>${item.turnover_rate}%</div><div>${item.fund.toFixed(0)}万</div></div>`;
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

function change_select() {page=1;getStockList();}

function get_stock_figure(code) {
    fetch(prefix + `/get?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                let title = `${data.data.name} - ${code} - ${data.data.region} - ${data.data.industry}`;
                let figure = document.getElementById("figure");
                figure.removeAttribute("_echarts_instance_")
                figure.innerHTML = '';
                let stockChart = echarts.init(figure);
                plot_k_line(stockChart, title, data.data.x, data.data.price, data.data.volumn, data.data.ma_five, data.data.ma_ten, data.data.ma_twenty, data.data.qrr, data.data.diff, data.data.dea, data.data.macd, data.data.k, data.data.d, data.data.j, data.data.trix, data.data.trma, data.data.turnover_rate, data.data.fund);
                document.getElementsByClassName("stock-chart")[0].style.display = "flex";
            }
        })
}

function query_stock_ai(code, name) {
    show_modal_cover();
    fetch(prefix + `/query/ai?code=${code}`)
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                // let s = `<div class="header">${name} - ${code}</div><div><div class="title">价格-3日均线</div><div class="value"><div><span>L3D: </span></div></div></div>`;
                document.getElementById("data-tips").innerText = `${code} - ${name} : ` + data.data;
                document.getElementsByClassName("stock-data")[0].style.display = "flex";
            }
            close_modal_cover();
        })
}

function show_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'flex';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'flex';}
function close_modal_cover() {document.querySelectorAll('.modal_cover')[0].style.display = 'none';document.querySelectorAll('.modal_cover>.modal_gif')[0].style.display = 'none';}

const overlay = document.querySelector('.stock-chart');
const overlay_data = document.querySelector('.stock-data');
overlay.addEventListener('click', function(event) { if (event.target === overlay) { overlay.style.display = 'none'; }});
overlay_data.addEventListener('click', function(event) {if (event.target === overlay_data) { overlay_data.style.display = 'none'; }});
document.getElementById("pre-page").disabled = 'true';
getStockList();
watchInput(document.getElementById('stock-name'), getStockList);
watchInput(document.getElementById('stock-code'), getStockList);
