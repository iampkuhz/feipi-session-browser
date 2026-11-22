/* Live-only local reference. Export templates do not load this script. */
(function () {
  'use strict';

  if (!/^https?:$/.test(window.location.protocol)
      || !['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)) return;

  const slug = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$/;
  const historicalName = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}(?::[A-Za-z0-9][A-Za-z0-9_.-]{0,100})*$/;

  async function reveal(name, status) {
    status.textContent = '正在请求 Finder 定位…';
    try {
      const response = await fetch('/api/local/skill-reference', {
        method: 'POST',
        headers: { 'X-Feipi-Skill-Reference': 'reveal' },
        body: name,
        mode: 'same-origin',
        redirect: 'error',
        cache: 'no-store'
      });
      status.textContent = response.status === 202
        ? '已请求在 Finder 中定位，请在 Finder 中打开所选文件。'
        : response.status === 404
          ? '在支持的本机位置未找到唯一的同名 SKILL.md。'
          : '暂时无法在本机定位。';
    } catch {
      status.textContent = '暂时无法在本机定位。';
    }
  }

  window.feipiSkillLookup = function (section, block) {
    if (block?.kind !== 'skills' || !Array.isArray(block.names)) return;
    const names = [...new Set(block.names.filter(name =>
      typeof name === 'string' && historicalName.test(name)))];
    if (!names.length) return;

    const details = document.createElement('details');
    const summary = document.createElement('summary');
    const note = document.createElement('p');
    const label = document.createElement('label');
    const picker = document.createElement('select');
    const button = document.createElement('button');
    const status = document.createElement('p');

    summary.textContent = '查看本机技能定义';
    note.textContent = '在 Finder 中定位本机安装的 SKILL.md。它不代表当时的版本，不计入当次上下文或 Token。';
    label.append('技能：', picker);
    picker.add(new Option('选择技能（可输入首字母）', ''));
    for (const name of names) picker.add(new Option(name, name));

    button.type = 'button';
    button.className = 'sd-btn sd-btn--secondary sd-btn--sm';
    button.textContent = '在 Finder 定位';
    button.disabled = true;
    status.setAttribute('role', 'status');

    picker.addEventListener('change', () => {
      const supported = slug.test(picker.value);
      button.disabled = !supported;
      status.textContent = picker.value && !supported
        ? '该技能带有插件命名空间，当前不支持从插件缓存定位。'
        : '';
    });
    button.addEventListener('click', async event => {
      if (!event.isTrusted || !slug.test(picker.value) || !names.includes(picker.value)) return;
      button.disabled = true;
      picker.disabled = true;
      try {
        await reveal(picker.value, status);
      } finally {
        picker.disabled = false;
        button.disabled = false;
      }
    });
    details.append(summary, note, label, ' ', button, status);
    section.append(details);
  };
})();
