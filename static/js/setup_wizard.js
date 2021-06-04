

const url = ""

const hostname=window.location.hostname;

//  init ui
update_ecr_access_card();
update_airflow_card();
update_server_card();
update_ui_card();
update_docker_card();
update_cron_card();



function update_ecr_access_card() {
  $.ajax({
    type: "GET",
    url: `${url}/update-manager/api/healthcheck/aws`,
    dataType: "json",
    data: {},
    success: function (val) {
      const aws_data = val && val.aws || {};
      generate_ecr_access_card(aws_data)
    },
  });
}

function update_airflow_card() {
  $.ajax({
    type: "GET",
    url: `${url}/update-manager/api/healthcheck/airflow`,
    dataType: "json",
    data: {},
    success: function (val) {
      const airflow_data = val && val.airflow || {};
      generate_airflow_card(airflow_data)
    },
  });
}


function update_server_card() {
  $.ajax({
    type: "GET",
    url: `${url}/update-manager/api/healthcheck/system`,
    dataType: "json",
    data: {},
    success: function (val) {
      const server_data = val && val.system || {};
      generate_server_card(server_data)
    },
  });
}

function update_ui_card() {
  $.ajax({
    type: "GET",
    url: `${url}/update-manager/api/healthcheck/ui`,
    dataType: "json",
    data: {},
    success: function (val) {
      const ui_data = val && val.ui || {};
      generate_ui_card(ui_data)
    },
  });
}

function update_docker_card() {
  $.ajax({
    type: "GET",
    url: `${url}/update-manager/api/healthcheck/containers`,
    dataType: "json",
    data: {},
    success: function (val) {
      const containers_data = val && val.containers || {};
      generate_docker_card(containers_data)
    },
  });
}

function update_cron_card() {
  $.ajax({
    type: "GET",
    url: `${url}/update-manager/api/healthcheck/cron`,
    dataType: "json",
    data: {},
    success: function (val) {
      const cron_data = val && val.cron || {};
      generate_cron_card(cron_data)
    },
  });
}




function generate_ecr_access_card(val) {
  aws_data = { ...val }
  const ecr_access_title_content = '<h2>ECR Access</h2>'

  let ecr_access_list_content_P = '';
  let ecr_access_list_content = '';
  let keyArray = [];
  let ecr_access_list_content_tootips = '';
  let isOneEmpty = false;
  Object.keys(aws_data).map(key => {
    if (key !== 'status' && key !== 'message' && (typeof aws_data[key] === 'string' || typeof aws_data[key] === 'number')) {
      ecr_access_list_content_P = ecr_access_list_content_P + `<p>${key}：${aws_data[key] || 'N/A'}</p>`;
      keyArray.push(key);
      if(aws_data[key]==='') isOneEmpty=true;
    }
    // else if (key !== 'status' && typeof aws_data[key] === 'object') {
    //   ecr_access_list_content_tootips = ecr_access_list_content_tootips + `<p id="${key}_tootips">${key}</p>`;
    // }
  })

  let ecr_access_status_content = ''
  if (aws_data && aws_data.status === 'OK') {
    ecr_access_status_content = '<div class=" card_status_success " id="aws_card_status_success" >' +
      '<img src="../static/asset/done_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">operational</span>' +
      '</div>'
  }

  if(aws_data && aws_data.status === 'FAILED'&&isOneEmpty){
    ecr_access_status_content = `<div class=" card_status_not_setup " title="${aws_data&&aws_data.message}">` +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">not setup</span>' +
      '</div>'
  }

  if(aws_data && aws_data.status === 'FAILED'&&!isOneEmpty){
    ecr_access_status_content = `<div class=" card_status_failed " id="aws_card_status_failed" title="${aws_data&&aws_data.message}">` +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">Failed</span>' +
      '</div>'
  }



  ecr_access_list_content = '<div class=" card_content_list ">' + ecr_access_list_content_P + ecr_access_list_content_tootips + '</div>'
  $(function () {
    $('#ecr_access_setting_button').on('click', () => settingClick('ECR Access', keyArray))
  })
  $('#ecr_access_card_content').append(ecr_access_title_content, ecr_access_status_content, ecr_access_list_content);
}

function generate_reverse_ssh_card(val) {
  ecr_ssh_data = { ...val }
  const reverse_ssh_title_content = '<h2>Reverse SSH</h2>'

  let reverse_ssh_list_content_P = '';
  let reverse_ssh_list_content = '';
  let reverse_ssh_key_array = [];
  let isOneEmpty = false;
  Object.keys(ecr_ssh_data).map(key => {
    if (key !== 'status' && key !== 'message' && typeof ecr_ssh_data[key] === 'string') {
      reverse_ssh_list_content_P = reverse_ssh_list_content_P + `<p>${key}：${ecr_ssh_data[key] || 'N/A'}</p>`;
      reverse_ssh_key_array.push(key);
      if(ecr_ssh_data[key]==='') isOneEmpty=true;
    }
  })


  let reverse_ssh_status_content = ''
  if (ecr_ssh_data && ecr_ssh_data.status === 'OK') {
    reverse_ssh_status_content = '<div class=" card_status_success ">' +
      '<img src="../static/asset/done_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">operational</span>' +
      '</div>'
  } 
  
  if(ecr_ssh_data && ecr_ssh_data.status === 'FAILED'&&isOneEmpty) {
    reverse_ssh_status_content = '<div class=" card_status_not_setup ">' +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">not setup</span>' +
      '</div>'
  }

  if(ecr_ssh_data && ecr_ssh_data.status === 'FAILED'&&!isOneEmpty) {
    reverse_ssh_status_content = '<div class=" card_status_failed ">' +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">Failed</span>' +
      '</div>'
  }


  reverse_ssh_list_content = '<div class=" card_content_list ">' + reverse_ssh_list_content_P + '</div>'
  $(function () {
    $('#reverse_ssh_setting_button').on('click', () => settingClick('Reverse SSH', reverse_ssh_key_array))
  })
  $('#reverse_ssh_card_content').append(reverse_ssh_title_content, reverse_ssh_status_content, reverse_ssh_list_content);
}


function generate_airflow_card(val) {
  // airflow card
  airflow_data = { ...val }
  const airflow_title_content = '<h2>Airflow Status</h2>'
  let airflow_status_content = ''
  if (airflow_data && airflow_data.status === 'OK') {
    airflow_status_content = '<div class=" card_status_success ">' +
      '<img src="../static/asset/done_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">operational</span>' +
      '</div>'
  } else {
    airflow_status_content = `<div class=" card_status_failed "  title="${airflow_data&&airflow_data.message}">` +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">not setup</span>' +
      '</div>'
  }
  const airflow_list_content = `<div class=" card_content_list "><p><a href="http://${hostname}:9080" style="color: aliceblue;">open airflow in new tab</a></p></div>`
  $('#airflow_card_content').append(airflow_title_content, airflow_status_content, airflow_list_content);
}

function generate_server_card(val) {
  //Server status
  server_data = { ...val }
  const server_title_content = '<h2>Server status</h2>'
  let server_status_content = ''
  if (server_data && server_data.status === 'OK') {
    server_status_content = '<div class=" card_status_success ">' +
      '<img src="../static/asset/done_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">operational</span>' +
      '</div>'
  } else {
    server_status_content = `<div class=" card_status_failed " title="${server_data&&server_data.message}">` +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">not setup</span>' +
      '</div>'
  }

  let server_list_content_P = '';
  let server_list_content = '';
  let server_list_content_tootips = '';
  // let reverse_ssh_key_array=[];
  Object.keys(server_data).map(key => {
    if (key !== 'status' && key !== 'message' && typeof server_data[key] === 'string') {
      server_list_content_P = server_list_content_P + `<p>${key}：${server_data[key] || 'N/A'}</p>`;
      // reverse_ssh_key_array.push(key);
    }
    // else if (key !== 'status' && typeof server_data[key] === 'object') {
    //   server_list_content_tootips = server_list_content_tootips + `<p id="${key}_tootips">${key}</p>`;
    // }
  })
  server_list_content = '<div class=" card_content_list ">' + server_list_content_P + '</div>'
  // server_list_content = '<div class=" card_content_list ">' + server_list_content_P + server_list_content_tootips + '</div>'
  $('#server_card_content').append(server_title_content, server_status_content, server_list_content);
}

function generate_ui_card(val) {
  // UI card
  ui_data = { ...val } 
  const UI_title_content = '<h2>UI Status</h2>'
  let UI_status_content = ''
  if (ui_data && ui_data.status === 'OK') {
    UI_status_content = `<div class=" card_status_success ">` +
      '<img src="../static/asset/done_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">operational</span>' +
      '</div>'
  } else {
    UI_status_content = `<div class=" card_status_failed " title="${ui_data&&ui_data.message}">` +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">Failed</span>' +
      '</div>'
  }

  const UI_list_content = `<div class=" card_content_list "><p><a href="https://${hostname}/CMDB" style="color: aliceblue;">open UI in new tab</a></p></div>`
  $('#ui_cad_content').append(UI_title_content, UI_status_content, UI_list_content);
}

function generate_docker_card(val) {
  // docker card
  docker_data = { ...val }
  const docker_title_content = '<h2>Docker Status</h2>'
  let docker_status_content = ''
  if (docker_data && docker_data.status === 'OK') {
    docker_status_content = '<div class=" card_status_success ">' +
      '<img src="../static/asset/done_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">operational</span>' +
      '</div>'
  } else {
    docker_status_content = `<div class=" card_status_failed " title="${docker_data&&docker_data.message}">` +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">not setup</span>' +
      '</div>'
  }
  const dataNum = val && val.data && val.data.length || 0;
  let dockerStr='docker running';
  if(dataNum>1) dockerStr='dockers running';
  const docker_list_content_p = '<div class="card_docker_summary">' +
    `<span style="margin-left: 1em;">${dataNum} ${dockerStr}  </span>` +
    // ` <button type="button" class="btn btn-primary" id='docker_detail_button'>${dataNum} ${dockerStr}</button>`
    '</div>'
  const docker_list_content = '<div class=" card_content_list " id="docker_summary_content">' + docker_list_content_p + '</div>'
  $(function () {
    $('#docker_summary_content').on('click', () => detailModalClick(docker_data&&docker_data.data||[]))
  })
  $('#docker_card_content').append(docker_title_content, docker_status_content, docker_list_content);
}

function generate_cron_card(val) {
  // docker card
  cron_data = { ...val }
  const cron_title_content = '<h2>Cron Status</h2>'
  let cron_status_content = ''
  if (cron_data && cron_data.status === 'OK') {
    cron_status_content = '<div class=" card_status_success ">' +
      '<img src="../static/asset/done_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">operational</span>' +
      '</div>'
  } else {
    cron_status_content = '<div class=" card_status_failed ">' +
      '<img src="../static/asset/report_problem_white_18dp.svg"/>' +
      '<span style="margin-left: 1em;">not setup</span>' +
      '</div>'
  }
  const cron_list_content = ''
  $('#cron_card_content').append(cron_title_content, cron_status_content, cron_list_content);
}


function settingClick(title, settings) {
  $('#myModal').modal('show');
  let key = '';
  if (title === 'ECR Access') key = 'aws';
  if (title === 'Reverse SSH') key = 'reverse_ssh';
  document.getElementById('myModalLabel').innerHTML = title;
  let settingsInput = '';
  settings.map(item => {
    settingsInput = settingsInput + `<input class='settings-input' type="text" placeholder=${item} name=${item} />`
  })
  document.getElementById('modal_main_body').innerHTML = '<div class="modal-main-content">' + settingsInput + '</div>'
  $(function () {
    $('#setting_save_button').on('click', function (e) {
      if (!e.isPropagationStopped()) {
        handleSave(key)
      }
      e.stopPropagation()
    });
  })

}

function closeSettingModal() {
  $('#myModal').modal('hide')
}

function detailModalClick(val){
  $('#myDetailModal').modal('show');
  document.getElementById('myDetailModalLabel').innerHTML = 'Docker Detail';
  let dockerDetail = '';
  val.map(item => {
    // console.log(JSON.stringify(item,null,'\t'))
    dockerDetail = dockerDetail +  `<p>${item.name}:    <img src="../static/asset/help_outline_black_18dp.svg" title='${JSON.stringify(item,null,'\t')}' /></p>`
  })
  document.getElementById('detail_modal_main_body').innerHTML = '<div class="modal-main-content">' + dockerDetail + '</div>'
}

function closeDetailModal() {
  $('#myDetailModal').modal('hide')
}

function handleSave(val) {
  const params = {};
  const inputs = document.getElementsByClassName('settings-input');
  for (i = 0; i < inputs.length; i++) {
    // params[inputs[i].name] = inputs[i].value;
    if (inputs[i].name === 'access_key') {
      params.aws_access_key = inputs[i].value;
    }
    if (inputs[i].name === 'secret_key') {
      params.aws_secret_key = inputs[i].value;
    }
  }
  $.ajax({
    type: "POST",
    url: `${url}/update-manager/api/${val}`,
    dataType: "json",
    data: JSON.stringify(params),
    // data:params,
    contentType: 'application/json',
    success: function (respoense) {
      // update ui
      closeSettingModal();
      if (val === 'aws') {
        $("#ecr_access_card_content").empty()
        update_ecr_access_card();
      }
    },
  });

}



