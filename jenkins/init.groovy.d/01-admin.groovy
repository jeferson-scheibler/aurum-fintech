import jenkins.model.*
import hudson.security.*

def jenkins = Jenkins.getInstance()
def realm = jenkins.getSecurityRealm()

if (realm instanceof HudsonPrivateSecurityRealm) {
    if (realm.getUser('admin') == null) {
        realm.createAccount('admin', 'admin123')
        jenkins.save()
        println "Admin criado."
    }
} else {
    def novoRealm = new HudsonPrivateSecurityRealm(false)
    novoRealm.createAccount('admin', 'admin123')
    jenkins.setSecurityRealm(novoRealm)

    def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
    strategy.setAllowAnonymousRead(false)
    jenkins.setAuthorizationStrategy(strategy)

    jenkins.save()
    println "Segurança configurada. Login: admin / admin123"
}
