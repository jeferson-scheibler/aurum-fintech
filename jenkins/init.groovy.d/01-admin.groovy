import jenkins.model.*
import hudson.security.*

def jenkins = Jenkins.getInstance()
def realm = jenkins.getSecurityRealm()

// Senha do admin vem da env JENKINS_ADMIN_PASSWORD (definida no docker-compose / .env).
// Se ausente, gera uma aleatória e imprime no log (apenas dev).
def senha = System.getenv('JENKINS_ADMIN_PASSWORD')
if (!senha || senha.length() < 6) {
    senha = UUID.randomUUID().toString()
    println "AVISO: JENKINS_ADMIN_PASSWORD nao definida. Senha aleatoria: ${senha}"
}

if (realm instanceof HudsonPrivateSecurityRealm) {
    if (realm.getUser('admin') == null) {
        realm.createAccount('admin', senha)
        jenkins.save()
        println "Admin criado."
    }
} else {
    def novoRealm = new HudsonPrivateSecurityRealm(false)
    novoRealm.createAccount('admin', senha)
    jenkins.setSecurityRealm(novoRealm)

    def strategy = new FullControlOnceLoggedInAuthorizationStrategy()
    strategy.setAllowAnonymousRead(false)
    jenkins.setAuthorizationStrategy(strategy)

    jenkins.save()
    println "Seguranca configurada. Usuario: admin"
}
