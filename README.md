Điểm yếu cốt lõi nằm ở luồng xác thực của GHTK:

Khi người dùng gửi yêu cầu đăng nhập với email và mật khẩu, API của GHTK sẽ kiểm tra thông tin đăng nhập. Nếu email và mật khẩu khớp với dữ liệu trong database, hệ thống sẽ tạo ra một JWT token và trả về cho client.

Vấn đề nằm ở chỗ: Hệ thống chỉ kiểm tra thông tin đăng nhập có đúng hay không, mà không kiểm tra xem tài khoản đó còn hoạt động hay không, shop đã bị khóa hay chưa. Điều này có nghĩa là ngay cả khi tài khoản đã bị vô hiệu hóa hoặc shop đã ngừng hoạt động, API vẫn trả về JWT token nếu thông tin đăng nhập đúng.

3. JWT Token Chứa Thông Tin Nhạy Cảm
Sau khi có được JWT token, vấn đề tiếp theo là cách GHTK cấu trúc token này. JWT token bao gồm ba phần: header, payload và signature, được mã hóa dưới dạng base64. Trong đó, phần payload chứa các thông tin về người dùng.

Điều nghiêm trọng là payload của JWT chứa số điện thoại thật của chủ tài khoản dưới dạng plain text. Cụ thể, payload chứa các trường như:

phone: Số điện thoại đăng ký của chủ shop

sub: Email đăng nhập

uid: Mã định danh người dùng trong hệ thống

i_uid: Mã định danh nội bộ khác

Vì JWT chỉ được encode bằng base64 mà không được mã hóa thêm, bất kỳ ai có được token đều có thể dễ dàng decode phần payload để đọc toàn bộ thông tin bên trong.

4. Ghép Nối Email Với Số Điện Thoại
Đây chính là điểm mấu chốt khiến lỗ hỏng trở nên nguy hiểm. Bình thường, các vụ data breach thường cho ra email và mật khẩu, nhưng không có số điện thoại đi kèm. Hoặc ngược lại, có số điện thoại nhưng không có email.

Thông qua lỗ hỏng này, kẻ tấn công có thể ghép nối được một cặp dữ liệu hoàn chỉnh: Từ email và mật khẩu mua được trên chợ đen, chúng có thể login vào GHTK, lấy JWT token, decode ra số điện thoại của chủ tài khoản đó. Như vậy, từ một mảnh dữ liệu rời rạc là email, kẻ tấn công có được số điện thoại thật của nạn nhân.

5. Mở Rộng Tấn Công Qua Phone Lookup
Sau khi có số điện thoại, kẻ tấn công có thể tiếp tục khai thác thông qua các dịch vụ tra cứu số điện thoại. Các dịch vụ này có thể cung cấp thêm nhiều thông tin cá nhân khác như:

Họ tên chủ thuê bao

Nhà mạng đang sử dụng

Loại thuê bao (trả trước hay trả sau)

Thời gian kích hoạt sim

Tình trạng thuê bao

Từ một email và mật khẩu, kẻ tấn công giờ đây có trong tay một hồ sơ cá nhân gần như hoàn chỉnh của nạn nhân, bao gồm email, số điện thoại, họ tên, và nhiều thông tin khác.
