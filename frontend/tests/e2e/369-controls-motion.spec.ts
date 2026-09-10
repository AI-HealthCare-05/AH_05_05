import {test,expect} from 'playwright/test';
test.setTimeout(45000);
test.use({viewport:{width:390,height:844}});
test.beforeEach(async({page})=>{await page.goto('/tests/harness/ui-motion.html');});
const insetCount=(value:string)=>(value.match(/inset/g)??[]).length;
const parseFirstCssColor=(value:string)=>{
 const srgb=value.match(/color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
 if(srgb)return srgb.slice(1,4).map(Number);
 const rgb=value.match(/rgba?\(\s*([\d.]+)[, ]+\s*([\d.]+)[, ]+\s*([\d.]+)/);
 if(!rgb)throw new Error(`CSS color not found: ${value}`);
 return rgb.slice(1,4).map(channel=>Number(channel)/255);
};
const luminance=(rgb:number[])=>rgb.map(channel=>channel<=.04045?channel/12.92:((channel+.055)/1.055)**2.4).reduce((sum,channel,index)=>sum+channel*[.2126,.7152,.0722][index],0);
const contrast=(a:number[],b:number[])=>{const [light,dark]=[luminance(a),luminance(b)].sort((x,y)=>y-x);return(light+.05)/(dark+.05);};
test('primary와 danger clay 윗면은 실제 글자색 대비를 4.5대1 이상 유지한다',async({page})=>{
 for(const button of [page.getByRole('button',{name:'저장',exact:true}),page.getByRole('button',{name:'삭제',exact:true})]){
  const appearance=await button.evaluate(el=>{const style=getComputedStyle(el);return{surface:style.backgroundImage,text:style.color};});
  expect(contrast(parseFirstCssColor(appearance.surface),parseFirstCssColor(appearance.text))).toBeGreaterThanOrEqual(4.5);
 }
});
test('공통 버튼과 카드는 밝은 윗면·아랫면 음영·짧은 외부 그림자를 함께 가진다',async({page})=>{
 const button=page.getByRole('button',{name:'저장',exact:true});
 const card=page.locator('.rx-card').filter({hasText:'표면 깊이'});
 for(const surface of [button,card]){
  const appearance=await surface.evaluate(el=>{const style=getComputedStyle(el);return{backgroundImage:style.backgroundImage,boxShadow:style.boxShadow,borderRadius:style.borderRadius};});
  expect(appearance.backgroundImage).not.toBe('none');
  expect(insetCount(appearance.boxShadow)).toBeGreaterThanOrEqual(2);
  expect(appearance.boxShadow).toMatch(/rgba?\(/);
  expect(Number.parseFloat(appearance.borderRadius)).toBeGreaterThanOrEqual(16);
 }
});
test('눌리는 공통 표면은 크기를 유지한 채 볼록 그림자에서 짧은 inset으로 들어간다',async({page})=>{
 for(const surface of [page.getByRole('button',{name:'저장',exact:true}),page.locator('.rx-card').filter({hasText:'눌리는 표면'})]){
  const beforeBox=await surface.boundingBox();
  const beforeShadow=await surface.evaluate(el=>getComputedStyle(el).boxShadow);
  const transitionProperties=await surface.evaluate(el=>getComputedStyle(el).transitionProperty.split(',').map(value=>value.trim()));
  expect(transitionProperties).toContain('box-shadow');
  expect(transitionProperties).toContain('transform');
  const point=beforeBox!;
  await page.mouse.move(point.x+point.width/2,point.y+point.height/2);await page.mouse.down();
  await expect.poll(()=>surface.evaluate(el=>getComputedStyle(el).boxShadow)).not.toBe(beforeShadow);
  expect(insetCount(await surface.evaluate(el=>getComputedStyle(el).boxShadow))).toBeGreaterThanOrEqual(2);
  await page.mouse.up();
  await expect.poll(()=>surface.evaluate(el=>getComputedStyle(el).transform)).toBe('none');
  expect(await surface.boundingBox()).toEqual(beforeBox);
 }
});
test('체크박스와 스위치도 바깥 hitbox를 칠하지 않고 같은 가벼운 곡면 명암을 쓴다',async({page})=>{
 const checkbox=page.getByRole('checkbox',{name:'동의'});
 const control=page.getByRole('switch',{name:'알림'});
 const thumb=control.locator('[data-slot="switch-thumb"]');
 expect(insetCount(await checkbox.evaluate(el=>getComputedStyle(el).boxShadow))).toBeGreaterThanOrEqual(2);
 expect(insetCount(await control.evaluate(el=>getComputedStyle(el,'::before').boxShadow))).toBeGreaterThanOrEqual(2);
 expect(insetCount(await thumb.evaluate(el=>getComputedStyle(el).boxShadow))).toBeGreaterThanOrEqual(1);
 await expect(control).toHaveCSS('background-color','rgba(0, 0, 0, 0)');
});
test('처리 중 버튼은 문구·크기를 유지하고 재입력을 막으며 완료 후 돌아온다',async({page})=>{
 const button=page.getByRole('button',{name:'저장',exact:true});
 const before=await button.boundingBox();
 const beforeSurface=await button.evaluate(el=>getComputedStyle(el).backgroundImage);
 await button.click();
 await expect(button).toHaveAttribute('aria-busy','true');
 await expect(button).toBeDisabled();
 await expect(button).toHaveText('저장');
 await expect(button.locator('[aria-hidden="true"]')).toBeVisible();
 await expect(button).toHaveCSS('background-color','rgb(242, 244, 245)');
 expect(await button.evaluate(el=>getComputedStyle(el).backgroundImage)).not.toBe(beforeSurface);
 const during=await button.boundingBox();
 expect(during?.width).toBe(before?.width);expect(during?.height).toBe(before?.height);
 await page.getByRole('button',{name:'테스트 요청 종료'}).click();
 await expect(button).toBeEnabled();
 await expect(button).not.toHaveAttribute('aria-busy','true');
 await page.waitForTimeout(500);
});
test('기존 primary hover는 gradient 아래에 숨지 않고 표면 자체가 진해진다',async({page})=>{
 const button=page.getByRole('button',{name:'저장',exact:true});
 const beforeSurface=await button.evaluate(el=>getComputedStyle(el).backgroundImage);
 await button.hover();
 await expect.poll(()=>button.evaluate(el=>getComputedStyle(el).backgroundImage)).not.toBe(beforeSurface);
});
test('CTA 눌림은 짧게 반응하고 움직임 줄이기에서는 위치를 움직이지 않는다',async({page})=>{
 const button=page.getByRole('button',{name:'저장',exact:true});
 const transitionProperties=await button.evaluate(el=>getComputedStyle(el).transitionProperty.split(',').map(value=>value.trim()));
 expect(transitionProperties).toContain('transform');
 expect(transitionProperties).toContain('box-shadow');
 await button.hover();await page.mouse.down();
 await expect.poll(()=>button.evaluate(el=>getComputedStyle(el).transform)).not.toBe('none');
 await page.mouse.move(0,0);await page.mouse.up();
 await page.emulateMedia({reducedMotion:'reduce'});
 await button.hover();await page.mouse.down();
 await expect(button).toHaveCSS('transform','none');
 await page.mouse.move(0,0);await page.mouse.up();
});
test('체크는 선택 의미를 유지하며 선택 후 선을 그리되 reduced motion은 정적이다',async({page})=>{
 const checkbox=page.getByRole('checkbox',{name:'동의'});
 await checkbox.check();await expect(checkbox).toBeChecked();
 expect(await checkbox.locator('svg path,svg polyline').evaluateAll(elements=>elements.some(el=>getComputedStyle(el).animationName!=='none'))).toBe(true);
 await page.emulateMedia({reducedMotion:'reduce'});
 await checkbox.uncheck();await checkbox.check();
 expect(await checkbox.locator('svg path,svg polyline').evaluateAll(elements=>elements.every(el=>getComputedStyle(el).animationName==='none'))).toBe(true);
});
test('스위치는 보이는 32px 트랙을 유지하면서 44px 터치 영역을 제공한다',async({page})=>{
 const control=page.getByRole('switch',{name:'알림'});
 const bounds=await control.boundingBox();
 expect(bounds?.width).toBe(56);
 expect(bounds?.height).toBeGreaterThanOrEqual(44);
 expect(await control.evaluate(el=>getComputedStyle(el,'::before').height)).toBe('32px');
 await control.click();
 await expect(control).toBeChecked();
 await page.emulateMedia({reducedMotion:'reduce'});
 expect(await control.evaluate(el=>getComputedStyle(el,'::before').transitionDuration)).toBe('0s');
 await expect(control.locator('[data-slot="switch-thumb"]')).toHaveCSS('transition-duration','0s');
 await page.waitForTimeout(500);
});
for(const kind of ['확인창','시트']){
 test(kind+' 열림/닫힘 모션이 있어도 포커스·Escape·입력이 유지된다',async({page})=>{
 const trigger=page.getByRole('button',{name:kind+' 열기'});
 await trigger.click();const dialog=page.getByRole('dialog',{name:kind,exact:true});
 await expect(dialog).toBeVisible();
 expect(await dialog.evaluate(el=>getComputedStyle(el).animationName)).not.toBe('none');
 await dialog.getByRole('textbox',{name:'메모'}).fill('보존할 메모');
 for(let i=0;i<5;i++){await page.keyboard.press('Tab');expect(await dialog.evaluate(el=>el.contains(document.activeElement))).toBe(true);}
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(trigger).toBeFocused();
 await page.emulateMedia({reducedMotion:'reduce'});await trigger.click();
 await expect(dialog).toHaveCSS('animation-name','none');
 await page.waitForTimeout(500);
 });
}
test('제어형 시트도 Escape로 닫히면 연 버튼에 포커스를 돌려준다',async({page})=>{
 const trigger=page.getByRole('button',{name:'알림 시간 설정 열기',exact:true});
 await trigger.click();
 await expect(page.getByRole('dialog',{name:'알림 시간 설정',exact:true})).toBeVisible();
 await page.keyboard.press('Escape');
 await expect(page.getByRole('dialog',{name:'알림 시간 설정',exact:true})).toHaveCount(0);
 await expect(trigger).toBeFocused();
});
