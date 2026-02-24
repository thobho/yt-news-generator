import { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import AppBar from '@mui/material/AppBar'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import Button from '@mui/material/Button'
import Box from '@mui/material/Box'
import IconButton from '@mui/material/IconButton'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import MenuIcon from '@mui/icons-material/Menu'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import { useAuth } from '../context/AuthContext'
import { useTenant } from '../context/TenantContext'

const navItems = [
  { label: 'Runs', path: '/' },
  { label: 'Analytics', path: '/analytics' },
  { label: 'Scheduler', path: '/scheduler' },
  { label: 'Logs', path: '/logs' },
  { label: 'Settings', path: '/settings' },
]

export default function Navbar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { logout, isAuthEnabled } = useAuth()
  const { tenants, currentTenant, setCurrentTenant } = useTenant()
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'))
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null)

  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget)
  }

  const handleMenuClose = () => {
    setAnchorEl(null)
  }

  return (
    <AppBar position="static" sx={{ mb: 3 }}>
      <Toolbar>
        <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', gap: 1 }}>
          <Typography
            variant="h6"
            component={Link}
            to="/"
            sx={{
              textDecoration: 'none',
              color: 'inherit',
              fontWeight: 'bold',
              whiteSpace: 'nowrap',
            }}
          >
            YT News Generator
          </Typography>

          {tenants.length > 0 && (
            <Select
              value={currentTenant?.id ?? ''}
              onChange={(e) => {
                const selected = tenants.find((t) => t.id === e.target.value)
                if (selected) {
                  setCurrentTenant(selected)
                  navigate('/')
                }
              }}
              variant="standard"
              disableUnderline
              sx={{
                color: 'inherit',
                fontWeight: 'bold',
                fontSize: '0.95rem',
                '& .MuiSelect-icon': { color: 'inherit' },
                '& .MuiSelect-select': { py: 0 },
              }}
            >
              {tenants.map((t) => (
                <MenuItem key={t.id} value={t.id}>
                  {t.display_name}
                </MenuItem>
              ))}
            </Select>
          )}
        </Box>

        {isMobile ? (
          <>
            <IconButton
              color="inherit"
              aria-label="menu"
              onClick={handleMenuOpen}
            >
              <MenuIcon />
            </IconButton>
            <Menu
              anchorEl={anchorEl}
              open={Boolean(anchorEl)}
              onClose={handleMenuClose}
            >
              <MenuItem
                component={Link}
                to="/new-run"
                onClick={handleMenuClose}
                sx={{ fontWeight: 'bold', color: 'secondary.main' }}
              >
                + New Run
              </MenuItem>
              {navItems.map((item) => (
                <MenuItem
                  key={item.path}
                  component={Link}
                  to={item.path}
                  onClick={handleMenuClose}
                  selected={location.pathname === item.path}
                >
                  {item.label}
                </MenuItem>
              ))}
              {isAuthEnabled && (
                <MenuItem onClick={() => { handleMenuClose(); logout(); }}>
                  Logout
                </MenuItem>
              )}
            </Menu>
          </>
        ) : (
          <Box sx={{ display: 'flex', gap: 1 }}>
            {navItems.map((item) => (
              <Button
                key={item.path}
                component={Link}
                to={item.path}
                color="inherit"
                sx={{
                  borderBottom: location.pathname === item.path ? '2px solid white' : 'none',
                  borderRadius: 0,
                }}
              >
                {item.label}
              </Button>
            ))}
            <Button
              component={Link}
              to="/new-run"
              variant="contained"
              color="secondary"
              sx={{ ml: 2 }}
            >
              + New Run
            </Button>
            {isAuthEnabled && (
              <Button color="inherit" onClick={logout} sx={{ ml: 1 }}>
                Logout
              </Button>
            )}
          </Box>
        )}
      </Toolbar>
    </AppBar>
  )
}
