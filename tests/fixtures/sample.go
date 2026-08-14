package data

import "context"

// UserRepo 用户仓储实现
// 提供用户的增删改查能力
type UserRepo struct{}

// Create 创建用户, 返回 *ent.User
func (r *UserRepo) Create(ctx context.Context) error {
	// TODO 这里需要处理并发
	name := "张三"          // 默认用户名
	return fmt.Errorf("创建用户失败: %w", nil)
}
