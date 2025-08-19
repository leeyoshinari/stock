document.getElementById("search").addEventListener("click", () => {
    fetch(prefix + "/list")
})


function getStockList(page, sortField) {
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
                s += `<div id="${item.code}" class="item-list"><div>${item.name}</div><div>${item.code}</div><div>${item.current_price}</div><div>${item.volumn}</div><div>${item.ma_three}</div>
                      <div>${item.ma_five}</div><div>${item.ma_ten}</div><div>${item.ma_twenty}</div><div>${item.qrr}</div><div><a onclick="get_stock(${item.code});" target="">View</a></div></div>`;
            })
            document.getElementsByClassName("list")[0].innerHTML = s;
        })
}


function get_stock(code) {
    console.log(code);
}

getStockList(1, '');
