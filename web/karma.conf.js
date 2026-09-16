// Cấu hình Karma.
//
// Angular CLI có cấu hình mặc định sẵn nên dự án không cần file này để chạy
// `ng test` trên máy dev. File này tồn tại vì đúng MỘT lý do: thêm launcher
// `ChromeHeadlessNoSandbox`.
//
// Chrome từ chối chạy sandbox khi không có quyền tạo namespace — đúng tình huống
// trong container Docker và trên GitHub Actions:
//
//   Failed to move to new namespace: PID namespaces supported,
//   Network namespace supported, but failed: errno = Operation not permitted
//
// Chạy bằng root cũng không cứu được (Chrome chặn thẳng: "Running as root
// without --no-sandbox is not supported"), nên không có cờ này thì test của web
// KHÔNG chạy được ở bất cứ đâu ngoài máy dev có Chrome cài sẵn.
//
// `--no-sandbox` an toàn ở đây vì test chỉ nạp mã của chính dự án trong một
// container dùng một lần — không có nội dung lạ nào để sandbox phải cách ly.

module.exports = function (config) {
  config.set({
    basePath: '',
    frameworks: ['jasmine', '@angular-devkit/build-angular'],
    plugins: [
      require('karma-jasmine'),
      require('karma-chrome-launcher'),
      require('karma-jasmine-html-reporter'),
      require('karma-coverage'),
      require('@angular-devkit/build-angular/plugins/karma'),
    ],
    reporters: ['progress', 'kjhtml'],
    browsers: ['ChromeHeadless'],
    customLaunchers: {
      ChromeHeadlessNoSandbox: {
        base: 'ChromeHeadless',
        flags: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
      },
    },
    restartOnFileChange: true,
  });
};
