import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-[3px] border text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-45',
  {
    variants: {
      variant: {
        default:
          'border-ink bg-ink text-paper hover:bg-ink-soft hover:border-ink-soft',
        outline: 'border-rule bg-sheet text-ink hover:border-ink-soft',
        ghost: 'border-transparent text-ink-soft hover:text-ink',
        signal:
          'border-signal bg-signal text-sheet hover:brightness-95 dark:text-paper',
      },
      size: {
        default: 'h-9 px-3.5',
        sm: 'h-7 px-2.5 text-xs',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

interface ButtonProps
  extends
    React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean | undefined
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  },
)
Button.displayName = 'Button'

export { Button }
