import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const source=readFileSync('../app/api/auth.py','utf8');
const html=source.split('LOGIN_PAGE_HTML = """')[1].split('"""')[0];
for(const width of [320,390,1280])test(`actual login template is labeled and fits ${width}px without account changes`,async({page},info)=>{
 let writes=0;await page.route('**/*',route=>{if(route.request().method()!=='GET')writes++;return route.fulfill({contentType:'text/html',body:html.replace('__ERROR__','')});});await page.setViewportSize({width,height:844});await page.goto('/login');await expect(page.getByLabel('اسم المستخدم',{exact:true})).toBeVisible();await expect(page.getByLabel('كلمة المرور',{exact:true})).toHaveAttribute('type','password');await page.getByRole('button',{name:'دخول',exact:true}).click();expect(writes).toBe(0);expect(await page.getByLabel('اسم المستخدم',{exact:true}).evaluate((e:HTMLInputElement)=>e.validity.valueMissing)).toBe(true);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();await page.screenshot({path:info.outputPath(`login-${width}.png`)});
});
